# DraftPilot-UI app

## Run the app

### uv

Run as a desktop app:

```
uv run flet run
```

Run as a web app:

```
uv run flet run --web
```

### UV

Install dependencies from `pyproject.toml`:

```
uv sync --all-groups --all-extras -U --all-packages
```

Run as a desktop app:

```
uv run flet run draftpilot-ui/src/main.py
```

Run as a web app:

```
uv run flet run draftpilot-ui/src/main.py --web
```

For more details on running the app, refer to the [Getting Started Guide](https://flet.dev/docs/getting-started/).

## Build the app

### Android

```
uv run flet build draftpilot-ui/src/main.py apk -v
```

For more details on building and signing `.apk` or `.aab`, refer to the [Android Packaging Guide](https://flet.dev/docs/publish/android/).

### iOS

```
uv run flet build draftpilot-ui/src/main.py ipa -v
```

For more details on building and signing `.ipa`, refer to the [iOS Packaging Guide](https://flet.dev/docs/publish/ios/).

### macOS

```
uv run flet build draftpilot-ui/src/main.py macos -v
```

For more details on building macOS package, refer to the [macOS Packaging Guide](https://flet.dev/docs/publish/macos/).

### Linux

```
uv run flet build draftpilot-ui/src/main.py linux -v
```

For more details on building Linux package, refer to the [Linux Packaging Guide](https://flet.dev/docs/publish/linux/).

### Windows

```
uv run flet build draftpilot-ui/src/main.py windows -v
```

For more details on building Windows package, refer to the [Windows Packaging Guide](https://flet.dev/docs/publish/windows/).
