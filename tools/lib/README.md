# Shared tools

Vetted, reusable scripts for this project and other Workstead projects.
`toolbox.json` pins each file's sha256. Changes need a maintainer's
approval (this is a protected path).

- `./ws tools list`: what's here, and whether each file matches its pin
- `./ws tools scan`: scripts elsewhere in the repository worth promoting
- `./ws tools promote PATH --name NAME`: add one (then submit as usual)
- `./ws tools find` / `./ws tools get NAME`: tools shared by trusted projects

See docs/toolbox.md in the Workstead template.
