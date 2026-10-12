# Signing the Windows launcher for PUBLIC distribution

Goal: make `MaritimeCyberRange.exe` run without the SmartScreen /
"unknown publisher" warning for arbitrary recipients.

## The honest landscape

| Cert type | Clears SmartScreen? | Private key form |
|---|---|---|
| **EV code-signing** | **Yes, immediately** | Hardware token (USB eToken) or cloud HSM |
| OV code-signing | Trusted, but SmartScreen still warns until the file earns **download reputation** | Hardware token / cloud HSM |
| Self-signed / internal CA | Only on machines that trust the cert (e.g. Group Policy) | Any (`.pfx` ok) |

**For "share with anyone", you want an EV certificate.** Buy from a CA
(DigiCert, Sectigo, SSL.com, GlobalSign, …); expect identity/organization
verification and ~$250–600/yr.

## Why you can't just hand me a `.pfx`

Since June 2023 the CA/Browser Forum requires the private key for **all**
publicly-trusted code-signing certs to stay on a FIPS-140 hardware token or in a
cloud HSM — it is **non-exportable**. So there is no `.pfx` to sign with on this
Linux box. Signing happens one of two ways:

### Option A — sign on Windows with the hardware token (simplest)
On a Windows machine with the token plugged in and the CA's tools installed:
```powershell
# Windows SDK provides signtool.exe
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a `
  MaritimeCyberRange.exe
signtool verify /pa /v MaritimeCyberRange.exe
```
`/a` auto-selects the cert on the token (you'll enter the token PIN). The
`/tr ... /td SHA256` adds a trusted timestamp so the signature stays valid after
the cert expires.

### Option B — cloud HSM signing (CI-friendly, no physical token)
Services like **DigiCert KeyLocker** or **SSL.com eSigner** hold the key in the
cloud and sign via their CLI (or a signtool KSP). Follow the provider's doc; the
signed `.exe` comes back the same.

## After signing
Replace the `.exe` inside the shipped package with the signed one:
```bash
# from the repo root, with the signed MaritimeCyberRange.exe in the current dir:
mkdir -p MaritimeCyberRange-windows && cp MaritimeCyberRange.exe MaritimeCyberRange-windows/
cd dist && zip MaritimeCyberRange-windows.zip MaritimeCyberRange-windows/MaritimeCyberRange.exe
```

## The Linux `sign-windows.sh` script in this folder
It uses `osslsigncode` with a `.pfx` or a self-signed cert. That path is for
**testing and internal/managed deployments only** — it will not help public
SmartScreen (no exportable `.pfx` for a real public cert, and self-signed isn't
publicly trusted). Keep it for internal Navy/iDEX machines where you push the
cert via Group Policy.

## Reality check on timing
Even a correctly EV-signed brand-new binary is trusted immediately by
SmartScreen; an **OV**-signed one is not, until enough people download it. Budget
for EV if "no warning on day one for everyone" is the requirement.
