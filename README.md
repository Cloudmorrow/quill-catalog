# The Quill Catalog

Every published [Quill](https://github.com/Cloudmorrow/cloudmorrow/blob/main/docs/QUILLS.md)
for Cloudmorrow, in one file: [`catalog.toml`](catalog.toml). A Cloudmorrow
server reads it (`quill_catalog` in the server config) to show you what you can
add, and installs a Quill as the tarball of the release pinned here.

## Adding your Quill

1. Build it — start from [`quill-template`](https://github.com/Cloudmorrow/quill-template).
2. Make sure `cm quill check`, `cm quill test` and `cm quill test --sandbox`
   pass, and tag a release (`v1.0.0`).
3. Open a pull request adding it here:

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

Updating is the same pull request with a new `ref`. The check on the pull
request fetches every Quill at its pinned release and checks it against the
pinned datamodels, the way a server does before it installs one.

## Categories

`personal`, `home`, `business`, `developer`. A new category is a pull request
too, with a line on why the others do not fit.
