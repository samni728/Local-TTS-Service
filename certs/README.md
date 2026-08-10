# Optional private CA certificates

Place a PEM-formatted proxy or company CA certificate in this directory only
when the service runs behind HTTPS inspection. For example:

```dotenv
TTS_CA_BUNDLE=/app/certs/company-ca.pem
```

The directory is mounted read-only by Docker Compose. Standard public VPS
deployments do not need a custom certificate.
