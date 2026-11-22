// « K-B » on one line everywhere, the search results included, and in a table a date and each word of the code too:
// the browser breaks a line after a hyphen, and the theme cuts the code of a table anywhere. Each is wrapped in a span
// that does not wrap (extra.css, .kb-nowrap); the text is unchanged, so the search index and the accessibility tree
// that Chrome builds stay the same.
const SKIPPED = "script, style, textarea, pre, svg, .mermaid, .kb-nowrap";
const KB = /K-B/g;
const DATE = /\b\d{4}-\d{2}(?:-\d{2})?(?![\d-])/g;
const WORD = /\S+/g;

function textNodesOf(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: node => (node.parentElement.closest(SKIPPED) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  return nodes;
}

// The nearest element around a text node that is not inline: a match is searched across the text of one such element,
// since a search result splits « K-B » into <mark>K</mark>-<mark>B</mark>.
function blockOf(node, root) {
  let element = node.parentElement;
  while (element !== root && getComputedStyle(element).display === "inline") element = element.parentElement;
  return element;
}

function groupByBlock(nodes, root) {
  const groups = new Map();
  for (const node of nodes) {
    const block = blockOf(node, root);
    if (!groups.has(block)) groups.set(block, []);
    groups.get(block).push(node);
  }
  return groups.values();
}

// The text node and the offset in it of a character of the joined text of a group.
function positionOf(nodes, starts, index) {
  let n = starts.length - 1;
  while (starts[n] > index) n--;
  return [nodes[n], index - starts[n]];
}

// A match is wrapped only when the elements it cuts at its two ends are <mark>s of a search result: a link or any
// other element is never split in two.
function cutsOnlyMarks(range) {
  const common = range.commonAncestorContainer;
  const top = common.nodeType === Node.TEXT_NODE ? common.parentElement : common;
  for (const boundary of [range.startContainer, range.endContainer]) {
    for (let element = boundary.parentElement; element !== top; element = element.parentElement) {
      if (element.tagName !== "MARK") return false;
    }
  }
  return true;
}

function wrapGroup(nodes, pattern) {
  const starts = [];
  let length = 0;
  for (const node of nodes) {
    starts.push(length);
    length += node.data.length;
  }
  const text = nodes.map(node => node.data).join("");
  // From the last match back: wrapping one changes only the text after its start.
  for (const match of [...text.matchAll(pattern)].reverse()) {
    const range = document.createRange();
    range.setStart(...positionOf(nodes, starts, match.index));
    const [endNode, endOffset] = positionOf(nodes, starts, match.index + match[0].length - 1);
    range.setEnd(endNode, endOffset + 1);
    // The text of the range is the match alone: no nested block nor skipped text lies between its characters.
    if (range.toString() !== match[0] || !cutsOnlyMarks(range)) continue;
    const span = document.createElement("span");
    span.className = "kb-nowrap";
    span.append(range.extractContents());
    range.insertNode(span);
    // A <mark> cut at the start or the end of the match can be left empty beside the span.
    for (const sibling of [span.previousSibling, span.nextSibling]) {
      if (sibling?.nodeType === Node.ELEMENT_NODE && sibling.tagName === "MARK" && sibling.textContent === "") {
        sibling.remove();
      }
    }
  }
}

function wrapMatches(root, pattern) {
  for (const group of groupByBlock(textNodesOf(root), root)) wrapGroup(group, pattern);
}

for (const code of document.querySelectorAll(".md-typeset table:not([class]) code")) wrapMatches(code, WORD);
for (const table of document.querySelectorAll(".md-typeset table:not([class])")) wrapMatches(table, DATE);
wrapMatches(document.body, KB);

// Material writes the search results after the page has loaded, at each search.
const searchResults = document.querySelector(".md-search-result__list");
if (searchResults) {
  const observer = new MutationObserver(() => {
    wrapMatches(searchResults, KB);
    // The records of this wrapping itself: they would only run the same search again.
    observer.takeRecords();
  });
  observer.observe(searchResults, { childList: true, subtree: true });
}
