// The list of the search results out of the Tab key (issue 654). Material makes it a Tab stop (tabindex="0"), but
// its own search closes on Tab before the focus moves: the focus then lands on the list folded, with no height, and
// vanishes. The results are reached by the arrow keys from the search field, and the text of the list stays read.
document.querySelector(".md-search__scrollwrap")?.setAttribute("tabindex", "-1");
