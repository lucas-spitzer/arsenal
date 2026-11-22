# Internal notes

These notes stay off the public repository so they do not leak confidential information about the platform and its plans. They stay on the machine that already has them. Git tracks this README only. Every other file here is ignored.

`git add -f` would publish those files again. Do not use it.

A new clone of this repository will not contain the notes. Copy them from the machine that has them if you need them on another computer.

Older commits on the public GitHub repository still contain the previous files. This ignore rule does not erase history.

## Cursor agents

The root [`.cursorignore`](../../.cursorignore) re-includes `docs/internal/**` so local Cursor agents can search and index these notes even though Git ignores them. That does not publish the files.

If Instant Grep still cannot find files here, turn off **Index Repositories for Instant Grep** and reload, or add this folder via **File → Add Folder to Workspace**. You can always `@`-mention an exact path.
