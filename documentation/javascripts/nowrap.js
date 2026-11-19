// « K-B » on one line everywhere, and in a table a date and each word of the code too: the browser breaks a line
// after a hyphen, and the theme cuts the code of a table anywhere. Each is wrapped in a span that does not wrap
// (extra.css, .kb-nowrap); the text is unchanged, so the search index and what a screen reader reads stay the same.
const SKIPPED = "script, style, textarea, pre, svg, .mermaid, .kb-nowrap";
const KB = /K-B/g;
const KB_OR_DATE = /K-B|(?<![\d-])\d{4}-\d{2}(?:-\d{2})?(?![\d-])/g;
const WORD = /\S+/g;

function wrapMatches(textNode, pattern) {
  const text = textNode.data;
  const parts = [];
  let end = 0;
  for (const match of text.matchAll(pattern)) {
    const span = document.createElement("span");
    span.className = "kb-nowrap";
    span.textContent = match[0];
    parts.push(text.slice(end, match.index), span);
    end = match.index + match[0].length;
  }
  if (parts.length === 0) return;
  parts.push(text.slice(end));
  textNode.replaceWith(...parts.filter(part => part !== ""));
}

function textNodesOf(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: node => (node.parentElement.closest(SKIPPED) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  return nodes;
}

for (const code of document.querySelectorAll(".md-typeset table:not([class]) code")) {
  textNodesOf(code).forEach(node => wrapMatches(node, WORD));
}
for (const node of textNodesOf(document.body)) {
  wrapMatches(node, node.parentElement.closest("table") ? KB_OR_DATE : KB);
}
