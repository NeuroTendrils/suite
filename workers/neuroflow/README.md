# NeuroFlow Worker

AGPL-3.0-licensed EEG preprocessing backend used by the NeuroTendrils
desktop suite. This directory is intentionally isolated from proprietary
suite code so it can later be exported (for example via `git subtree
split`).

## License

NeuroFlow is free software under the GNU Affero General Public License
v3.0. You can use, study, and modify it; if you distribute a modified
version (including over a network), you must provide the corresponding
source under AGPL-3.0. See [`LICENSE`](LICENSE).

The NeuroTendrils desktop suite GUI remains proprietary and talks to
this worker as a separate process.