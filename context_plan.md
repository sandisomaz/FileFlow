# Implementation Plan: Metadata Propagation

## Goal
Improve identification of generic files (CV, Cover Letter) by using the "context" of their sibling files in the same directory.

## Strategy
1.  **Group by Directory**: When staging files, group them by their `parent` path.
2.  **Find Anchor**: In each directory group, look for a file with strong metadata (e.g., Z83 form with a "Position").
3.  **Propagate**: Apply that "Position" to all other files in the same directory that differ (e.g., are "Unclassified").

## Changes to `StagingManager`
-   Add `self.folder_groups = {}` to track files by folder.
-   Implement `_resolve_folder_contexts()` method.
-   Call resolution logic before generating the preview.
