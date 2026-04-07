# deltaforge

Generates text files on GitHub release and uploads them as release assets.

Files:
- `ALL_FILES.jar` - all generated files for the release
- `CHANGED_FILES.jar` - only added/modified files compared to the previous release

Flow:
- `tools/generate_txt_files.py` generates the current files
- `tools/diff_generated_files.py` compares them with the previous release
- `tools/create_archives.py` builds both jars
- `.github/workflows/release-generated-files.yml` runs this on release publish and uploads the jars

Tested with simulated releases `v0.1.0` to `v0.4.0`.
