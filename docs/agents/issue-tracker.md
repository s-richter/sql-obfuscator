# Issue Tracker: GitHub

Issues and PRDs live in GitHub Issues. Use the `gh` CLI from this repo.

## Conventions

- Create: `gh issue create --title "..." --body-file <path>`
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state open`
- Comment: `gh issue comment <number> --body "..."`
- Add label: `gh issue edit <number> --add-label "..."`
- Remove label: `gh issue edit <number> --remove-label "..."`
- Close: `gh issue close <number> --comment "..."`

When a skill says "publish to the issue tracker", create a GitHub issue.
When a skill says "fetch the relevant ticket", run `gh issue view <number> --comments`.
