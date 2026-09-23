# Security Policy

## Supported Versions

We release patches for security vulnerabilities. The following versions are currently supported:

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |
| < 1.0   | :x:                |



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
   `connect.py` will not run unless `APPROVED = True` is set. Read this document before enabling it.

6. **Keep dependencies up to date.**
   Regularly update GStreamer, `nmap`, and Python to their latest stable versions.

7. **Run in a controlled environment.**
   Use a virtual machine or isolated network when testing unknown devices.

8. **Be aware of network scanning laws.**
   Running `nmap` or probing ports on networks you do not own may be illegal in your jurisdiction.

## Known Security Considerations

- The tool probes port 554 and attempts to connect to RTSP streams. This activity may be logged by network monitoring systems.
- The path lists in `connect.py` may include placeholders for default credentials. **These are not real credentials** but are well-known defaults used by many cameras. Before publishing, ensure they are removed or replaced with user-supplied input.
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