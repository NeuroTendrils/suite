# EMOTIV Insight setup and validation

Suite supports the five Insight EEG channels in canonical order **AF3, T7, Pz, T8,
AF4**, sampled at **128 Hz**. Raw Cortex/EMOTIV CSV EEG is in microvolts; the adapter
converts it to volts for MNE. Counters, quality, motion and markers are excluded
from EEG features. Numeric marker columns become events. Interpolated samples
and timestamp gaps are marked as bad annotations for epoch rejection. Gaps are
boundaries in the imported sample timeline; elapsed wall-clock gaps are not
reconstructed or silently resampled.

## Set up acquisition

1. Install EMOTIV Launcher from EMOTIV, sign in and connect exactly one Insight.
   Check electrode contact and EEG quality there before collecting data.
2. Register a Cortex application and obtain raw EEG access. Raw EEG subscription
   requires a paid license and an active session. Suite requests one session debit
   during authorization; license terms and availability are managed by EMOTIV.
3. Supply `EMOTIV_CLIENT_ID` and `EMOTIV_CLIENT_SECRET` to the backend process
   environment, then restart Suite from that environment. For development, set
   these variables in your terminal before `npm run dev:suite`. Do not commit
   credentials, put them in a study, or paste them into subject metadata.
4. Cortex listens at `wss://localhost:6868`. Suite verifies TLS and bypasses HTTP
   proxies for this local connection. If Python cannot find the EMOTIV Root CA,
   set `EMOTIV_CA_CERT` to the trusted PEM from EMOTIV. Certificate checks stay on.
5. Open a study → NeuroFlow → Import → EMOTIV Insight. Set a 2–30 second capture,
   check the recording/session consent box and choose **Capture Insight EEG**.
   If prompted, approve the application in Launcher and retry. Capture never
   starts automatically, and consent resets after a successful capture.
6. Review the staged file and confirm 128 Hz, choose a pseudonymous subject label,
   then **Import recording**. Inspect the signal before preprocessing and epochs.

Capture is a bounded acquisition into a local CSV, followed by import. It does
not provide continuous live inference or live robot control. The robot driver
continues to reject the live source. The BCI Lab can replay predictions from a
trained model on an imported labeled dataset. Captured spontaneous EEG has no
class labels: use a task protocol with numeric markers in an exported recording
or add reviewed event annotations before building a classification dataset.

## Import existing CSV

EMOTIV CSVs with all five `EEG.<channel>` headers, or an EMOTIV/Insight metadata
preamble plus the five channel headers, are recognized automatically. Columns
may be reordered. Verify the CSV is raw microvolt EEG, not power spectra or
normalized values. Suite pre-fills 128 Hz but requires confirmation. Exports with
conflicting sample-rate metadata, non-finite EEG, inconsistent row widths or
non-monotonic timestamps are rejected. Other delimited files use the existing
explicit column-role import.

## Models and research evidence

New experiments use `research_auto`: class-balanced logistic regression across
four regularization values, plus shrinkage LDA when training folds have enough
samples per class. Scaling and model selection happen inside training folds.
Subject groups are preferred, then session groups; single-session CV is explicitly
flagged. If group folds cannot represent all classes, a fixed baseline is fitted.
Small datasets may only support logistic regression. This is a reproducible
baseline workflow, not a pretrained EEG decoder or a guarantee of accuracy.
EEGNet, Deep4 and ShallowFBCSP remain unimplemented catalog entries.

The explicit train/validation/test partitions must be disjoint and belong to the
same dataset. Evaluation never substitutes another partition for an empty one
and counts unseen held-out labels as errors. Outputs include accuracy, balanced
accuracy, macro F1, Cohen's kappa, class support, a confusion matrix and a Wilson
95% accuracy interval. The interval is trial-level and can be optimistic for
correlated trials. Prediction probabilities are uncalibrated estimator scores.
Explanations use validation data when available; otherwise test data is clearly
identified as inspected. Do not tune a model after inspecting its final test set.

Insight has no C3/C4 motor-cortex electrodes. The simulated C3/C4 motor-imagery
demo cannot validate a model for Insight. Collect artifact-reviewed, labeled
Insight recordings over multiple sessions, evaluate on untouched sessions and
participants, and compare to a majority-class/chance baseline before claiming
research performance. Eye and muscle artifacts can be predictive confounds.
No physical Insight or licensed Cortex session was available during implementation;
protocol tests use a fake socket. Hardware validation must still verify channel
order, electrode quality, known marker timing, dropouts, reconnects and real-data
held-out performance. No research-grade performance claim is established.

Band power now uses correctly normalized one-sided Welch PSD integration rather
than the earlier unwindowed FFT estimate. Rebuild datasets and retrain models when
switching feature versions. New bundles record the extraction method and reject
incompatible datasets; legacy bundles cannot establish that method provenance.

## Privacy and retention

EEG capture, model training and inference stay local in Suite. Cortex itself
communicates with EMOTIV services and has separate account/data policies. Suite
does not control EMOTIV's retention or account settings.

New backend files use an owner-only process umask. Captures and JSON writes are
owner-only; JSON replacement is atomic to avoid truncating saved studies. This is
OS file protection, not encryption. Existing files, external originals, backups,
cloud-synced folders and other software using your OS account keep their existing
permissions and access. Use full-disk encryption and an appropriate local workspace.

Captures persist under `studies/<study>/captures`; imported FIFs, datasets and
models persist under their corresponding study folders until deliberately removed.
There is no automatic deletion or retention timer. Original source files outside
the workspace are preserved. Suite does not erase existing user data as part of
this update.

**Report & export defaults to a redacted summary**: aggregate counts and selected
numeric metrics only, with no participant labels, free-text metadata, local paths,
raw signals or model binaries. Disabling redaction allows JSON metadata; additionally
including data/binaries allows recordings, models and reports. Log files and
symlinks are excluded. Each study export gets a separate filename. Model bundles
are a separate sensitive export and include parameters, class labels and paths.
Counts and scores can still identify small cohorts by context; review before sharing.

## Primary references

- [Insight hardware specifications](https://www.emotiv.com/tools/knowledge-base/insight-troubleshooting/how-to-get-good-contact-quality-with-insight)
- [Cortex connection and Root CA](https://emotiv.gitbook.io/cortex-api/connecting-to-the-cortex-api)
- [Application approval](https://emotiv.gitbook.io/cortex-api/authentication/requestaccess)
- [Authorization and session debit](https://emotiv.gitbook.io/cortex-api/authentication/authorize)
- [Active sessions](https://emotiv.gitbook.io/cortex-api/session/createsession)
- [Raw EEG subscription requirements](https://emotiv.gitbook.io/cortex-api/data-subscription/subscribe)
- [Stream columns, EEG units and quality](https://emotiv.gitbook.io/cortex-api/data-subscription/data-sample-object)
- [Welch spectral density](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html)
- [Cross-validation and held-out evaluation](https://scikit-learn.org/stable/modules/cross_validation.html)
