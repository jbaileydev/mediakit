# TODO

## qBittorrent source hardening for Mediadeck

- [ ] Apply `QBitTorrentSearchOptions.min_seeders` when collecting search results.
- [ ] Keep cancelled search jobs queryable and clean up completed background task references without discarding results clients may still need.
- [ ] Identify newly added torrents deterministically instead of selecting an arbitrary hash from a before/after snapshot, including when additions happen concurrently.
- [ ] Handle torrent-monitor polling errors by marking acquisition jobs failed with an informative status message and exposing task failures through job status.
- [ ] Decide how to persist or reconcile search and acquisition jobs across API restarts.
- [ ] Align the qBittorrent search-job/status/cancel behavior with the `MediaSource` protocol, or provide a consistent adapter for Mediadeck.
- [ ] Add automated tests for connection, search and acquisition lifecycle, seeder filtering, cancellation/timeouts, duplicates, concurrent additions, monitor errors, and seeding preference.

## YouTube source parity for Mediadeck

- [ ] Complete the YouTube package migration and exports. The implementation is in `sources/youtube.py`, but `mediakit.sources.youtube` resolves to the separate `sources/youtube/` package, whose initializer currently does not export `YouTubeSource`; importing it from the package fails.
- [ ] Align YouTube source APIs, result/job models, and status values with the current `MediaSource` protocol and shared async job models.
- [ ] Implement and validate all declared search options: search type, safe search, channel and upload-date filters, duration bounds, and maximum result count. Handle unknown/zero durations deliberately.
- [ ] Add managed search jobs with status/result retrieval, cancellation, timeout handling, visible failures, and completed-task cleanup to match the qBittorrent search workflow.
- [ ] Make every acquisition option effective, including audio/video quality selection, media variant, playlist behavior, subtitles, metadata, thumbnails, overwrite, and output directory.
- [ ] Harden download task lifecycle and progress reporting: retain task handles, provide cancellation, safely surface progress-hook errors, and ensure failures/cancellation always reach a terminal job status.
- [ ] Report actual final output paths and metadata reliably for postprocessed downloads and playlists, rather than relying only on intermediate progress-hook filenames.
- [ ] Decide how to persist or reconcile acquisition/search job state and active downloads across API restarts.
- [ ] Add automated tests for package imports, search filters/options, job lifecycle, downloads/progress/errors/cancellation, output paths, playlists, and metadata.
