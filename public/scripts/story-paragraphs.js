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

  const linkGranddaddysArch = () => {
    const main = document.querySelector('main');
    if (!main) return;

    const exactName = /Granddaddy(?:'|’)s Arch/g;
    const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent) return NodeFilter.FILTER_REJECT;
        if (parent.closest('a, summary, h1, h2, h3, h4, h5, h6')) return NodeFilter.FILTER_REJECT;
        return exactName.test(node.nodeValue || '') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });

    const matches = [];
    while (walker.nextNode()) matches.push(walker.currentNode);

    for (const textNode of matches) {
      const text = textNode.nodeValue || '';
      const fragment = document.createDocumentFragment();
      let lastIndex = 0;
      exactName.lastIndex = 0;

      for (const match of text.matchAll(exactName)) {
        const index = match.index ?? 0;
        fragment.append(text.slice(lastIndex, index));
        const link = document.createElement('a');
        link.className = 'reference-link';
        link.href = 'https://www.redrivergorgearches.com/';
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = match[0];
        fragment.append(link);
        lastIndex = index + match[0].length;
      }

      fragment.append(text.slice(lastIndex));
      textNode.replaceWith(fragment);
    }
  };

  linkGranddaddysArch();
})();
