# Security Policy

### Use this tool at your own risk
You acknowledge and agree that your use of this software is at your sole risk and that you assume full responsibility for any and all consequences, damages, or legal liabilities that may arise from your use of the software

**⚠️ LEGAL WARNING**
This tool is intended **only** for use on your own network and on
devices you own or have explicit, written permission to test.
Unauthorized access to camera systems, network scanning, or credential
testing is illegal in many jurisdictions.
By using this tool you accept that it will be used only on your own
network and for **educational and lab purposes**.
The authors and contributors assume no liability for misuse or damage
caused by this software.

### Fix "[!] not approved for use"
Once you have read this file and agree with the terms:

Open `linux/connect.py` 
At `line 24` change the variable `APPROVED` = True

## Supported Versions

We release patches for security vulnerabilities. The following versions are currently supported:

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |
| < 1.0   | :x:                |


## Reporting a Vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

Report them privately using:

- GitHub private advisory: https://github.com/jacobP-cyberdev/camera-viewer-rtsp/security/advisories/new

Include:

- Type of issue
- Full paths of affected source files
- Steps to reproduce
- Proof-of-concept if applicable
- Impact assessment

## Policy

- We will acknowledge receipt of your vulnerability report within 48 hours.
- We will provide a more detailed response within 5 business days.
- We will keep you informed about our progress.
- We will credit you in the release notes if you wish.

## Security Best Practices for Users

This tool is designed for **authorized testing and personal use only**. To use it safely:

1. **Only use on devices you own or have explicit permission to test.**
   Unauthorized access to camera systems is illegal in many jurisdictions.

2. **Use only on your own network.**
   Do not run this tool against networks, subnets, or devices you do not control.

3. **Never hardcode credentials in the source code.**
   If you modify the script, use environment variables, a configuration file outside version control, or prompt the user at runtime.

4. **Do not commit real credentials or personal data.**
   Use `.gitignore` to exclude `.env`, `config.ini`, `*.log`, and similar files.

5. **Enable the approval gate.**
   On Linux, `linux/connect.py` will not run unless `APPROVED = True` is set.

6. **Keep dependencies up to date.**
   Regularly update GStreamer, `nmap`, and Python to their latest stable versions.

7. **Run in a controlled environment.**
   Use a virtual machine or isolated network when testing unknown devices.

8. **Be aware of network scanning laws.**
   Running `nmap` or probing ports on networks you do not own may be illegal in your jurisdiction.

## Known Security Considerations

- The tool probes port 554 and attempts to connect to RTSP streams. This activity may be logged by network monitoring systems.
- The tool does not encrypt or store any credentials; they are passed directly to GStreamer. Ensure your local environment is secure.
- No authentication, authorization, or access control is performed by this tool. It is a viewer and diagnostic utility, not a hardened service.

## Disclosure Policy

When we receive a security bug report, we will:

1. Confirm the problem and determine affected versions.
2. Audit code to find any similar problems.
3. Prepare fixes for all supported versions.
4. Release new versions as soon as possible.

We will publicly disclose the vulnerability after a fix has been released, unless there is a compelling reason to delay.

## Comments on this Policy

If you have suggestions on how this process could be improved, please submit a pull request.