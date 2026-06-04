# P2P Planner v1.0.0-beta.2 — release artifact README template

This folder is a lightweight source-controlled template for the beta.2 release artifacts. It is not the final binary payload.

Final GitHub assets should be attached to the `v1.0.0-beta.2` Pre-release:

- `p2p-planner-v1.0.0-beta.2-web-win64.zip`
- `p2p-planner-v1.0.0-beta.2-linux-x86_64.AppImage`
- `release-gates_*.zip`
- `SHA256SUMS.txt`

## Windows quick start expectation

1. Unzip `p2p-planner-v1.0.0-beta.2-web-win64.zip`.
2. Start PostgreSQL via the bundled `docker-compose.dev.yml` or configure `backend/.env`.
3. Run `backend/p2p-planner-backend.exe`.
4. Serve/open the bundled frontend build as documented by the final artifact.
5. Open the app, sign up/sign in, and create a workspace, board, column and card.

## Linux AppImage quick start expectation

```bash
chmod +x p2p-planner-v1.0.0-beta.2-linux-x86_64.AppImage
./p2p-planner-v1.0.0-beta.2-linux-x86_64.AppImage
```

The AppImage must clearly document whether it bundles the backend/frontend launcher only or also expects an external PostgreSQL runtime.

## Beta note

This is a beta/pre-release artifact line. The source-level release-gates checkpoint passed, but stable `v1.0.0` requires repeatability evidence and artifact-level smoke checks on the uploaded platform packages.
