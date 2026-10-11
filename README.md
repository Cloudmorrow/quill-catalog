# The Quill Catalog

Every published [Quill](https://github.com/Cloudmorrow/cloudmorrow/blob/main/docs/QUILLS.md)
for Cloudmorrow, in one file: [`catalog.toml`](catalog.toml). A Cloudmorrow
server reads it (`quill_catalog` in the server config) to show you what you can
add, and installs a Quill as the tarball of the release pinned here. The file
on `main` is the one thing servers read, and this repository's history is the
record of every release a server could ever install.

## Adding your Quill

1. Build it — start from [`quill-template`](https://github.com/Cloudmorrow/quill-template)
   with GitHub's *Use this template*, or `cm quill new <id>`.
2. Make sure `cm quill check`, `cm quill test` and `cm quill test --sandbox`
   pass, and release it: push a tag (`v1.0.0`, the same as `version` in
   `quill.toml`), publish a release on github.com, or run the **release**
   workflow in your repository's Actions tab. The template's workflow checks
   and tests it once more and publishes the release.
3. Open a pull request here adding one block to `catalog.toml` (the pull
   request template carries it):

```toml
[[quills]]
id = "plants"
name = "Plants"
summary = "Your plants, and when you last watered each."
repo = "https://github.com/you/quill-plants"
ref = "v1.0.0"
category = "home"
publisher = "you"
```

The check on the pull request fetches every Quill at its pinned release and
checks it against the pinned datamodels, the way a server does before it
installs one. One of us reads the Quill at that release and merges the pull
request, or says what is in the way. Merged, it is on every server's list
and on [cloudmorrow.com/quills](https://cloudmorrow.com/quills) within the hour.

## Updating it

Release the new version the same way. Within fifteen minutes the
**releases** workflow here sees it and opens a pull request moving your
`ref` to it, with the check result and the install sheet — what a server
shows an administrator before installing — in its body. We merge it, or
close it with a word on why. You may open that pull request yourself
instead; the result is the same. A release that was turned down is not
proposed again; the next release is.

Until the pull request is merged, servers keep installing the release the
catalog pins.

## Cloudmorrow's own Quills

A Quill whose repository is `github.com/Cloudmorrow/quill-*` is ours, and
reaches the catalog with no review and no further step: the same workflow
takes its release and commits it to `main`, a new Quill included, with its
name, summary and category from its `quill.toml`. The template is excluded.

The foundational datamodels ([`Cloudmorrow/datamodels`](https://github.com/Cloudmorrow/datamodels))
move the same way, but only when every Quill still checks out against the
new release; otherwise the pin stays and the run names the Quill that
breaks.

Nobody edits refs by hand any more: [`scripts/follow.py`](scripts/follow.py)
is the only writer of them. The `foundation` flag and the categories are
product decisions, and stay hand edits.

## Categories

`personal`, `home`, `business`, `developer`. A new category is a pull request
too, with a line on why the others do not fit.
