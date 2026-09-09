# GitHub CI and CD

These workflows run on GitHub-hosted virtual machines. Their configuration is YAML under `.github/workflows/`; individual steps run Python, PowerShell, and shell commands. No local computer or webcam needs to remain connected.

| Workflow | Trigger | Result |
| --- | --- | --- |
| `CI` | Push to `main`, pull request targeting `main`, or manual run | Windows Python, Godot, synthetic bridge/adapter, and report UI checks |
| `CD` | Manual run | The same checks, Windows package build, extracted-package tests, downloadable artifact; no Release publication |
| `CD` | Push a version tag such as `v0.1.9` | The same checks and package validation, then an experimental GitHub prerelease with ZIP and SHA256 |
| `Windows checks and package` | Called by CI/CD | Shared Windows 2022 / Python 3.12 implementation |

Open the repository's **Actions** tab, select **CI** or **CD**, and choose **Run workflow** to start a manual run. Select a completed CD run and download its **windows-package** artifact. It is retained for seven days and contains the application ZIP, checksum, and release notes. Extract the downloaded artifact, then extract the application ZIP before launching the game.

## Publishing a version

Use the public checkout. The tag must exactly match `shadowmma.__version__`, use the form `vMAJOR.MINOR.PATCH`, and point to a commit in `main` history. For example, when the application version is `0.1.9`:

```powershell
git switch main
git pull --ff-only
git tag -a v0.1.9 -m "Experimental ShadowMMA 0.1.9"
git push origin v0.1.9
```

Tag publication is an intentional release action. A manual CD run only produces an artifact, even when run against a tag. An invalid tag, failed test, dirty/different package source, or checksum mismatch stops the pipeline. The workflow does not overwrite an existing Release; inspect a failed rerun instead of deleting or moving an already published tag.

The Release is marked **prerelease** because human motion recognition is still unreliable. A successful workflow does not establish recognition accuracy, physical latency, or professional coaching quality.

## Runtime and permissions

The test/build job uses the standard GitHub-hosted `windows-2022` runner. The small publishing job uses `ubuntu-24.04`. Python dependencies, the pose model, and Godot are installed in the runner using the project's pinned setup. Tests use generated observations; no physical webcam or real user footage is involved. Only the verified distribution and release notes are uploaded as artifacts; test image/report directories are not uploaded.

CI and package jobs have `contents: read`. Only the tag-triggered publishing job has `contents: write`, using GitHub's automatic token. No personal access token, cloud account, deployment server, or extra repository secret is required. Third-party actions are pinned to commit hashes, and checkout does not retain Git credentials. Public pull requests run as `pull_request`, not `pull_request_target`.

GitHub currently provides standard hosted runner execution free for public repositories; larger runners have separate billing. These workflows use standard runners with timeouts and short artifact retention. See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

References: [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) and [reusing workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows).
