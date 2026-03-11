document.addEventListener("DOMContentLoaded", function () {
  var svg = d3.select("#graph-canvas");
  var wrapper = document.querySelector(".graph-canvas-wrapper");
  var tooltip = document.getElementById("graph-tooltip");
  var emptyMsg = document.getElementById("graph-empty");
  var width = wrapper.clientWidth;
  var height = wrapper.clientHeight;

  svg.attr("width", width).attr("height", height);

  // Responsive resize
  var resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      width = wrapper.clientWidth;
      height = wrapper.clientHeight;
      svg.attr("width", width).attr("height", height);
      if (simulation) simulation.force("center", d3.forceCenter(width / 2, height / 2)).alpha(0.3).restart();
    }, 150);
  });

  var simulation, nodeElements, edgeElements, labelElements;
  var activeFilters = { post: true, semantic: true, episodic: true, tag: true };
  var graphData;

  fetch("/graph/data")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      graphData = data;
      if (!data.nodes || data.nodes.length === 0) {
        emptyMsg.classList.remove("hidden");
        return;
      }
      render(data);
      bindControls();
    })
    .catch(function (err) {
      console.error("graph fetch error:", err);
      emptyMsg.textContent = "Failed to load graph data.";
      emptyMsg.classList.remove("hidden");
    });

  function render(data) {
    var g = svg.append("g");

    // Zoom + pan
    var zoom = d3.zoom()
      .scaleExtent([0.2, 4])
      .on("zoom", function (event) { g.attr("transform", event.transform); });
    svg.call(zoom);
    svg.on("dblclick.zoom", function () {
      svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
    });

    // Arrow marker
    svg.append("defs").append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -3 6 6")
      .attr("refX", 18)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-3L6,0L0,3")
      .attr("fill", "var(--text-secondary)");

    // Build link/node index for D3
    var nodeMap = {};
    data.nodes.forEach(function (n) { nodeMap[n.id] = n; });
    var links = data.edges.filter(function (e) {
      return nodeMap[e.source] && nodeMap[e.target];
    });

    // Force simulation
    simulation = d3.forceSimulation(data.nodes)
      .force("link", d3.forceLink(links).id(function (d) { return d.id; })
        .distance(function (d) {
          if (d.edge_type === "tag") return 120;
          if (d.edge_type === "memory-post") return 90;
          return 60;
        }))
      .force("charge", d3.forceManyBody().strength(-180))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide(22))
      .alphaDecay(0.02);

    // Edges
    edgeElements = g.append("g").attr("class", "edges")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("class", function (d) { return "graph-edge edge-" + d.rel + " etype-" + d.edge_type; })
      .attr("marker-end", function (d) { return d.rel === "follows_from" ? "url(#arrow)" : null; });

    // Node groups
    nodeElements = g.append("g").attr("class", "nodes")
      .selectAll("g")
      .data(data.nodes)
      .join("g")
      .attr("class", function (d) {
        var cls = "graph-node ntype-" + d.type;
        d.special_tags.forEach(function (t) { cls += " special-" + t; });
        return cls;
      })
      .call(d3.drag()
        .on("start", dragStarted)
        .on("drag", dragged)
        .on("end", dragEnded));

    // Draw shapes per type
    nodeElements.each(function (d) {
      var el = d3.select(this);
      if (d.type === "post") {
        el.append("rect")
          .attr("width", 14).attr("height", 10)
          .attr("x", -7).attr("y", -5)
          .attr("rx", 1);
      } else if (d.type === "tag") {
        el.append("circle").attr("r", 3);
      } else {
        var r = d.type === "semantic" ? 7 : 5;
        el.append("circle").attr("r", r);
        if (d.special_tags.indexOf("open-question") >= 0) {
          el.append("circle").attr("r", r + 3)
            .attr("class", "open-question-ring");
        }
      }
    });

    // Labels for post and tag nodes
    labelElements = g.append("g").attr("class", "labels")
      .selectAll("text")
      .data(data.nodes.filter(function (d) { return d.type === "post" || d.type === "tag"; }))
      .join("text")
      .attr("class", function (d) { return "graph-label label-" + d.type; })
      .text(function (d) {
        var maxLen = d.type === "tag" ? 20 : 30;
        return d.label.length > maxLen ? d.label.slice(0, maxLen) + "..." : d.label;
      });

    // Tick
    simulation.on("tick", function () {
      edgeElements
        .attr("x1", function (d) { return d.source.x; })
        .attr("y1", function (d) { return d.source.y; })
        .attr("x2", function (d) { return d.target.x; })
        .attr("y2", function (d) { return d.target.y; });

      nodeElements.attr("transform", function (d) { return "translate(" + d.x + "," + d.y + ")"; });

      labelElements
        .attr("x", function (d) { return d.x; })
        .attr("y", function (d) { return d.y - 12; });
    });

    // Hover tooltip
    nodeElements.on("mouseenter", function (event, d) {
      var html = '<strong class="tooltip-type">' + d.type + "</strong>";
      html += '<div class="tooltip-label">' + escapeHtml(d.label) + "</div>";
      if (d.detail) html += '<div class="tooltip-detail">' + escapeHtml(d.detail) + "</div>";
      if (d.tags.length) html += '<div class="tooltip-tags">' + d.tags.map(function (t) { return "#" + t; }).join(" ") + "</div>";
      if (d.created_at) html += '<div class="tooltip-date">' + d.created_at.slice(0, 10) + "</div>";
      if (d.view_count != null) html += '<div class="tooltip-views">' + d.view_count + " views</div>";

      tooltip.innerHTML = html;
      tooltip.classList.remove("hidden");
      positionTooltip(event);
    })
    .on("mousemove", positionTooltip)
    .on("mouseleave", function () { tooltip.classList.add("hidden"); });

    // Click navigation for posts
    nodeElements.on("click", function (event, d) {
      if (d.url) window.location = d.url;
    });
    nodeElements.style("cursor", function (d) { return d.url ? "pointer" : "default"; });
  }

  function positionTooltip(event) {
    var x = event.clientX + 12;
    var y = event.clientY + 12;
    if (x + 280 > window.innerWidth) x = event.clientX - 292;
    if (y + 200 > window.innerHeight) y = event.clientY - 212;
    tooltip.style.left = x + "px";
    tooltip.style.top = y + "px";
  }

  function dragStarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }

  function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }

  function dragEnded(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }

  function bindControls() {
    // Filter buttons
    document.querySelectorAll(".graph-filter-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var type = btn.dataset.filter;
        activeFilters[type] = !activeFilters[type];
        btn.classList.toggle("active");
        applyFilters();
      });
    });

    // Search
    var searchInput = document.querySelector(".graph-search");
    if (searchInput) {
      searchInput.addEventListener("input", function () {
        var q = searchInput.value.toLowerCase().trim();
        if (!q) {
          nodeElements.classed("graph-node-dim", false);
          edgeElements.classed("graph-edge-dim", false);
          labelElements.classed("graph-label-dim", false);
          return;
        }
        nodeElements.classed("graph-node-dim", function (d) {
          return d.label.toLowerCase().indexOf(q) < 0;
        });
        edgeElements.classed("graph-edge-dim", true);
        labelElements.classed("graph-label-dim", function (d) {
          return d.label.toLowerCase().indexOf(q) < 0;
        });
      });
    }
  }

  function applyFilters() {
    var visibleIds = {};
    nodeElements.each(function (d) {
      var visible = activeFilters[d.type] !== false;
      d3.select(this).classed("hidden", !visible);
      if (visible) visibleIds[d.id] = true;
    });
    edgeElements.classed("hidden", function (d) {
      var sid = typeof d.source === "object" ? d.source.id : d.source;
      var tid = typeof d.target === "object" ? d.target.id : d.target;
      return !visibleIds[sid] || !visibleIds[tid];
    });
    labelElements.classed("hidden", function (d) { return !visibleIds[d.id]; });
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }
});
