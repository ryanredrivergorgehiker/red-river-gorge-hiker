(() => {
  const paragraphBreaks = {
    'lilis-leap': [4, 7, 10, 17, 23, 28],
    'the-day-the-gorge-took-13-hours': [5, 14, 21, 30, 36],
    'the-blank-places-on-the-map': [4, 10, 17, 21, 28, 33],
    'the-fletcher-ridge-hunt': [4, 9, 14, 18, 22, 27],
    'granddaddys-arch': [6, 12, 15],
    'walking-home': [5, 14, 21, 27, 32]
  };

  const regroupStory = (details, breaks) => {
    const body = details.querySelector('.story-body');
    if (!body) return;

    const sourceParagraphs = Array.from(body.children).filter(
      (element) => element instanceof HTMLParagraphElement
    );
    if (sourceParagraphs.length === 0) return;

    const fragments = sourceParagraphs.map((paragraph) => paragraph.innerHTML.trim());
    const grouped = [];
    let start = 0;

    for (const end of breaks) {
      if (end > start && end <= fragments.length) {
        grouped.push(fragments.slice(start, end).join(' '));
        start = end;
      }
    }

    if (start < fragments.length) grouped.push(fragments.slice(start).join(' '));

    const replacement = document.createDocumentFragment();
    for (const html of grouped) {
      const paragraph = document.createElement('p');
      paragraph.innerHTML = html;
      replacement.appendChild(paragraph);
    }

    body.replaceChildren(replacement);
  };

  for (const [id, breaks] of Object.entries(paragraphBreaks)) {
    const details = document.getElementById(id);
    if (details instanceof HTMLDetailsElement) regroupStory(details, breaks);
  }
})();
