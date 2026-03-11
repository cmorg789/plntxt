document.addEventListener("DOMContentLoaded", function () {
    if (typeof markdownit === "undefined" || typeof DOMPurify === "undefined") {
        return;
    }

    var md = markdownit({
        html: false,
        linkify: true,
        typographer: true,
        highlight: function (str, lang) {
            if (lang && typeof hljs !== "undefined" && hljs.getLanguage(lang)) {
                try {
                    return hljs.highlight(str, { language: lang }).value;
                } catch (_) {}
            }
            return "";
        },
    });

    function renderMarkdownElements() {
        var elements = document.querySelectorAll(".markdown-content");
        for (var i = 0; i < elements.length; i++) {
            var el = elements[i];
            if (el.getAttribute("data-rendered") === "true") {
                continue;
            }

            var source;
            if (el.hasAttribute("data-markdown")) {
                source = el.getAttribute("data-markdown");
            } else {
                source = el.textContent;
            }

            var rendered = md.render(source);
            el.innerHTML = DOMPurify.sanitize(rendered, {
                ADD_TAGS: ["highlight"],
                ADD_ATTR: ["class"],
            });
            el.setAttribute("data-rendered", "true");
        }
    }

    renderMarkdownElements();

    // Re-render after HTMX swaps new content into the page
    document.body.addEventListener("htmx:afterSwap", function () {
        renderMarkdownElements();
    });
});
