# IT Certificate Guide — DITA Converter Tool

**Audience:** IT Administrator  
**Purpose:** Generate a self-signed code-signing certificate, sign the DITAConverter.exe, and push the certificate to all workplace machines so Windows trusts the executable without SmartScreen warnings.  
**Time required:** ~30 minutes  
**Cost:** $0

---

## Overview

Without a trusted certificate, Windows displays:

> *"Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognised app from starting."*

Users with no technical knowledge cannot bypass this. The solution:

1. Generate a self-signed certificate (one-time, on IT admin machine)
2. Sign the `.exe` with that certificate (done by developer on every new build)
3. Push the certificate to all workplace machines via Group Policy (one-time, for the whole org)

After step 3, every machine in your domain trusts any `.exe` signed with your certificate — no SmartScreen, no warnings, ever.

---

## Prerequisites

- Windows machine with **Windows SDK** installed (for `signtool.exe` and `makecert` / `New-SelfSignedCertificate`)
- Domain Administrator rights (for Group Policy deployment)
- PowerShell 5.1+ (built into Windows 10/11)

---

## Step 1 — Generate the Self-Signed Certificate

Run **PowerShell as Administrator** on the IT admin machine:

```powershell
# Create the certificate
# Replace "Yourcompany IT" with your actual organisation name
$cert = New-SelfSignedCertificate `
    -Type CodeSigning `
    -Subject "CN=YourCompany DITA Converter, O=YourCompany IT, C=AU" `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -HashAlgorithm SHA256 `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -NotAfter (Get-Date).AddYears(5)

# Confirm it was created
Write-Host "Certificate thumbprint: $($cert.Thumbprint)"
```

---

## Step 2 — Export the Certificate to a .pfx File

The `.pfx` file contains both the certificate and the private key. The developer needs this file to sign new builds.

```powershell
# Set a strong password — share this securely with the developer (not by email)
$password = ConvertTo-SecureString -String "YourStrongPassword123!" -Force -AsPlainText

# Export the .pfx (certificate + private key)
Export-PfxCertificate `
    -Cert "Cert:\CurrentUser\My\$($cert.Thumbprint)" `
    -FilePath "C:\Certs\DITAConverter.pfx" `
    -Password $password

Write-Host "PFX exported to C:\Certs\DITAConverter.pfx"
```

> **Security:** Store `DITAConverter.pfx` securely. Anyone with this file and password can sign executables that your machines will trust. Do not commit it to Git.

---

## Step 3 — Export the Public Certificate (.cer)

The `.cer` file is the public certificate only (no private key). This is what gets deployed to all machines.

```powershell
Export-Certificate `
    -Cert "Cert:\CurrentUser\My\$($cert.Thumbprint)" `
    -FilePath "C:\Certs\DITAConverter.cer" `
    -Type CERT

Write-Host "CER exported to C:\Certs\DITAConverter.cer"
```

---

## Step 4 — Deploy Certificate to All Machines via Group Policy

This makes every machine in your domain trust the certificate. Do this once — all future builds signed with the same certificate are automatically trusted.

### 4a. Open Group Policy Management

1. Press `Win + R` → type `gpmc.msc` → press Enter
2. Right-click your domain (or target OU) → **Create a GPO in this domain, and Link it here**
3. Name it: `DITA Converter Code Signing Trust`
4. Right-click the new GPO → **Edit**

### 4b. Add the Certificate

In the Group Policy Management Editor:

```
Computer Configuration
  └── Policies
        └── Windows Settings
              └── Security Settings
                    └── Public Key Policies
                          └── Trusted Publishers
```

1. Right-click **Trusted Publishers** → **Import**
2. Browse to `C:\Certs\DITAConverter.cer`
3. Click Next → Next → Finish

Repeat the same import under:
```
Public Key Policies → Trusted Root Certification Authorities
```

> Adding to both **Trusted Publishers** and **Trusted Root Certification Authorities** ensures Windows fully trusts the certificate at every verification level.

### 4c. Force Group Policy Update (optional — otherwise updates on next login)

To push immediately to all machines without waiting for the next login cycle:

```powershell
# Run on each target machine, or push via remote PowerShell
gpupdate /force
```

---

## Step 5 — Verify on a Test Machine

On any domain-joined machine after the GPO applies:

```powershell
# Check that the certificate is in the trusted store
Get-ChildItem "Cert:\LocalMachine\TrustedPublisher" | 
    Where-Object { $_.Subject -like "*DITA Converter*" }
```

You should see the certificate listed. Then double-click `DITAConverter.exe` — no SmartScreen prompt should appear.

---

## Developer Workflow — Signing New Builds

The developer runs this command after each build. They need:
- `DITAConverter.pfx` (from IT, stored securely — not in Git)
- The `.pfx` password (shared securely by IT)

```cmd
python build/build.py --sign --cert "C:\Certs\DITAConverter.pfx" --cert-password "YourStrongPassword123!"
```

Or manually with signtool:

```cmd
signtool sign ^
  /f "C:\Certs\DITAConverter.pfx" ^
  /p "YourStrongPassword123!" ^
  /fd SHA256 ^
  /tr http://timestamp.digicert.com ^
  /td SHA256 ^
  /v ^
  dist\DITAConverter.exe
```

### Verify the signature

```cmd
signtool verify /pa /v dist\DITAConverter.exe
```

Expected output:
```
Successfully verified: dist\DITAConverter.exe
```

---

## Certificate Renewal

The certificate is valid for **5 years** from creation. Before it expires:

1. Repeat Steps 1–3 to generate a new certificate
2. Repeat Step 4 to deploy the new `.cer` via Group Policy
3. The developer signs new builds with the new `.pfx`

> **Note:** Existing signed `.exe` files remain valid after the certificate expires as long as they were timestamped during the valid period. The `--tr` (timestamp) flag in the signing command handles this automatically.

---

## Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| SmartScreen still appears after GPO | GPO not yet applied | Run `gpupdate /force` on the machine |
| `signtool` not found | Windows SDK not installed | Install from: aka.ms/buildtools |
| "Certificate not trusted" error | `.cer` not in Trusted Root | Repeat Step 4b for Trusted Root CA |
| Signature verification fails | Wrong timestamp URL | Use `http://timestamp.digicert.com` |
| PFX password rejected | Wrong password | Confirm password with IT — it is case-sensitive |

---

## Summary Checklist

- [ ] Certificate generated (Steps 1–2) — `.pfx` stored securely with IT
- [ ] Public `.cer` exported (Step 3)
- [ ] GPO created and `.cer` deployed to Trusted Publishers + Trusted Root CA (Step 4)
- [ ] GPO verified on test machine — no SmartScreen on signed exe (Step 5)
- [ ] `.pfx` file shared securely with developer (not via email, not in Git)
- [ ] Developer can sign builds using `build.py --sign`
- [ ] Certificate renewal date noted: _______________
