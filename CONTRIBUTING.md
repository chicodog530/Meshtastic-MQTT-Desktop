# Contributing

Thank you for helping improve Meshtastic MQTT Desktop.

## Reporting a problem

Include the operating system, Python and application versions, action performed, expected and actual behavior, relevant Diagnostics lines, and whether the packet used JSON or encrypted protobuf.

Remove passwords, private keys, messages, and precise locations before posting logs or screenshots.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -v
```

## Pull requests

1. Create a focused branch.
2. Keep protocol logic outside GUI callbacks when practical.
3. Add or update tests for parser, encryption, or packet-building changes.
4. Run unit tests and `py_compile` before submitting.
5. Update README and CHANGELOG when user-visible behavior changes.

Do not commit personal configuration, contacts, logs, packet captures, private credentials, or private PSKs.
