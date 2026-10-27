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

## The review

Every release of a Quill that is not Cloudmorrow's is reviewed before the
catalog takes it, the first and every one after. Part of it is rules the
workflow applies to every pull request, whoever opened it; a release that
breaks one is turned down with the reason, and the next release is looked
at afresh:

- the release is a tag `vMAJOR.MINOR.PATCH`, the same as `version` in
  `quill.toml`, and newer than the one the catalog pins;
- its licence is open source (AGPL, GPL, LGPL, MIT, Apache, BSD, MPL, ISC,
  EUPL, Unlicense or CC0);
- the publisher and the repository are the ones the catalog has; a Quill
  that changes hands or moves is a pull request from its new publisher that
  says so;
- the check passes: every Quill at its pin, against the pinned datamodels.

The rest is a person reading the Quill at that release — what it adds,
what it reaches, what code it runs — helped by the pull request's list of
what changed in the ways that matter: code where there was none, a new
service, webhook or API, a host it reaches, a secret it reads, a datamodel
it adds or extends. What is turned down there gets a word on why.

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
is the only writer of them. `standard = true` puts a Quill in the
installer's and the setup page's list; the script writes it on every Quill
of Cloudmorrow's own. `foundation = true` ticks it there to begin with
(Files, Calendar, Notes and Tasks), which is also what a server nobody
asked gets at first boot; that flag and the categories are product
decisions, and stay hand edits. Everything else is added from
Administration once the server runs.

## Categories

`personal`, `home`, `business`, `developer`. A new category is a pull request
too, with a line on why the others do not fit.
