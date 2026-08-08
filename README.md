# Red River Gorge Hiker

Static Astro website for the public photography brand of Ryan D. Lewis. The preview is designed for GitHub Pages and does not configure the custom domain.

## Commands

```sh
npm ci
npm run dev
npm run check
python3 -m unittest discover -s tests -p 'test*.py'
```

## Content and assets

The five approved Google Drive Website Content documents, six watermarked Website Exports, transparent logo, and two approved QR files were unavailable in this environment on 2026-08-06. Missing final text is explicitly marked in the preview. No substitute photography, logo, or QR code was created. See `src/data/assets.ts` and the asset-directory READMEs.

GitHub Pages cannot provide true server-side hotlink prevention. The interface discourages casual dragging and context-menu use within artwork containers, but screenshots and copying cannot be absolutely prevented.

## Deployment

CI checks pull requests. The Pages workflow intentionally deploys only `main` (or an approved manual run); it does not merge feature branches or configure a `CNAME`. Consequently, this draft branch cannot provide a Pages preview without an explicitly approved alternative or merge.

## Branch protection recommendations

Require a pull request, one approving review, successful `CI / test`, conversation resolution, and no force pushes or branch deletion on `main`. Keep workflow permissions read-only except the Pages deployment job's narrowly scoped `pages: write` and `id-token: write` permissions.

## Source parameters

`/prints/?source=hungry-hiker` and `/prints/?source=rockhouse` render normally. Site code neither stores nor analyzes these non-personal parameters.
