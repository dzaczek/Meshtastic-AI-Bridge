with open("templates/index.html", "r") as f:
    content = f.read()

start_idx = content.find("// ── ANALYTICS ─────────────────────────────────────────────────────────────")
end_idx = content.find("// ── CONFIG TAB ────────────────────────────────────────────────")

if start_idx != -1 and end_idx != -1:
    replace = """// ── ANALYTICS (D3) ─────────────────────────────────────────────────────────────
let analyticsHeatmap = null;

function clearD3(selector) {
  const el = document.querySelector(selector);
  if (el) el.innerHTML = '';
}

function drawBarChart(data, selector, xLabel, yLabel, color) {
  clearD3(selector);
  const container = document.querySelector(selector);
  const margin = {top: 10, right: 10, bottom: 20, left: 40};
  const width = container.clientWidth - margin.left - margin.right;
  const height = container.clientHeight - margin.top - margin.bottom;

  const svg = d3.select(selector).append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand()
    .domain(data.map(d => d.label))
    .range([0, width])
    .padding(0.2);

  const y = d3.scaleLinear()
    .domain([0, d3.max(data, d => d.value)])
    .nice()
    .range([height, 0]);

  svg.append("g")
    .attr("transform", `translate(0,${height})`)
    .call(d3.axisBottom(x).tickSize(0))
    .selectAll("text")
    .style("fill", "var(--text)")
    .style("font-size", "10px");

  svg.append("g")
    .call(d3.axisLeft(y).ticks(5).tickSizeOuter(0))
    .selectAll("text")
    .style("fill", "var(--muted)")
    .style("font-size", "10px");

  svg.selectAll(".domain, .tick line")
    .style("stroke", "var(--border)");

  svg.selectAll("rect")
    .data(data)
    .enter()
    .append("rect")
    .attr("x", d => x(d.label))
    .attr("y", d => y(d.value))
    .attr("width", x.bandwidth())
    .attr("height", d => height - y(d.value))
    .attr("fill", color)
    .attr("rx", 2);
}

function drawDoughnutChart(data, selector, colors) {
  clearD3(selector);
  const container = document.querySelector(selector);
  const width = container.clientWidth;
  const height = container.clientHeight;
  const radius = Math.min(width, height) / 2 - 10;

  const svg = d3.select(selector).append("svg")
    .attr("width", width)
    .attr("height", height)
    .append("g")
    .attr("transform", `translate(${width / 2},${height / 2})`);

  const pie = d3.pie().value(d => d.value).sort(null);
  const arc = d3.arc().innerRadius(radius * 0.5).outerRadius(radius);

  const path = svg.selectAll("path")
    .data(pie(data))
    .enter()
    .append("path")
    .attr("d", arc)
    .attr("fill", (d, i) => colors[i])
    .attr("stroke", "var(--bg)")
    .style("stroke-width", "2px");

  // Add labels inside arc if there's space
  svg.selectAll("text")
    .data(pie(data))
    .enter()
    .append("text")
    .attr("transform", d => `translate(${arc.centroid(d)})`)
    .attr("text-anchor", "middle")
    .style("fill", "#fff")
    .style("font-size", "10px")
    .style("font-weight", "bold")
    .text(d => d.data.value > 0 ? d.data.label : "");
}

function drawBubbleChart(data, selector, colorScheme) {
  clearD3(selector);
  const container = document.querySelector(selector);
  if(!container) return;
  const width = container.clientWidth;
  const height = container.clientHeight;

  const pack = d3.pack()
    .size([width, height])
    .padding(3);

  const root = d3.hierarchy({children: data})
    .sum(d => d.count);

  const nodes = pack(root).leaves();

  const svg = d3.select(selector).append("svg")
    .attr("width", width)
    .attr("height", height);

  const node = svg.selectAll("g")
    .data(nodes)
    .enter().append("g")
    .attr("transform", d => `translate(${d.x},${d.y})`);

  const color = d3.scaleOrdinal(colorScheme);

  node.append("circle")
    .attr("r", d => d.r)
    .style("fill", (d,i) => color(i))
    .style("fill-opacity", 0.7)
    .style("stroke", (d,i) => color(i))
    .style("stroke-width", 1)
    .append("title")
    .text(d => `${d.data.name || d.data.id}\\n${d.data.count} packets`);

  node.append("text")
    .attr("dy", "-0.2em")
    .style("text-anchor", "middle")
    .style("font-size", d => Math.min(d.r / 3, 12) + "px")
    .style("fill", "#fff")
    .style("pointer-events", "none")
    .text(d => (d.r > 15) ? (d.data.name || d.data.id).substring(0, 10) : "");

  node.append("text")
    .attr("dy", "1em")
    .style("text-anchor", "middle")
    .style("font-size", d => Math.min(d.r / 3, 10) + "px")
    .style("fill", "rgba(255,255,255,0.7)")
    .style("pointer-events", "none")
    .text(d => (d.r > 20) ? d.data.count : "");
}

function drawForceDirectedGraph(linksData, selector, color) {
  clearD3(selector);
  const container = document.querySelector(selector);
  if(!container) return;
  const width = container.clientWidth;
  const height = container.clientHeight;

  // Build nodes from links
  const nodesMap = new Map();
  linksData.forEach(l => {
    if (!nodesMap.has(l.from)) nodesMap.set(l.from, { id: l.from, name: l.from_name || l.from });
    if (!nodesMap.has(l.to)) nodesMap.set(l.to, { id: l.to, name: l.to_name || l.to });
  });

  const nodes = Array.from(nodesMap.values());
  const links = linksData.map(l => ({
    source: l.from,
    target: l.to,
    value: l.count
  }));

  const svg = d3.select(selector).append("svg")
    .attr("width", width)
    .attr("height", height);

  const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(50))
    .force("charge", d3.forceManyBody().strength(-150))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collide", d3.forceCollide().radius(20));

  const maxVal = d3.max(links, d => d.value) || 1;

  const link = svg.append("g")
    .attr("stroke", "var(--border-s)")
    .attr("stroke-opacity", 0.6)
    .selectAll("line")
    .data(links)
    .enter().append("line")
    .attr("stroke-width", d => Math.max(1, (d.value / maxVal) * 5))
    .append("title")
    .text(d => `${d.value} packets`);

  const node = svg.append("g")
    .selectAll("g")
    .data(nodes)
    .enter().append("g")
    .call(d3.drag()
      .on("start", (e, d) => {
        if (!e.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on("drag", (e, d) => {
        d.fx = e.x; d.fy = e.y;
      })
      .on("end", (e, d) => {
        if (!e.active) simulation.alphaTarget(0);
        d.fx = null; d.fy = null;
      }));

  node.append("circle")
    .attr("r", 8)
    .attr("fill", color)
    .attr("stroke", "var(--bg)")
    .attr("stroke-width", 1.5)
    .append("title")
    .text(d => d.name);

  node.append("text")
    .attr("x", 10)
    .attr("y", 3)
    .style("font-size", "10px")
    .style("fill", "var(--text)")
    .text(d => d.name);

  simulation.on("tick", () => {
    svg.selectAll("line")
      .attr("x1", d => d.source.x)
      .attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x)
      .attr("y2", d => d.target.y);

    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });
}

async function initAnalytics() {
  const days = document.getElementById('analytics-days').value;
  try {
    const r = await fetch(`/api/analytics/packets?days=${days}`);
    if (!r.ok) return;
    const data = await r.json();

    // 1. Hourly Bar
    const hData = Object.keys(data.hourly).map(h => ({ label: `${h}:00`, value: data.hourly[h] }));
    drawBarChart(hData, '#d3-an-hourly', 'Time', 'Packets', '#4488ff');

    // 2. Types Bar
    const tData = (data.top_types||[]).map(t => ({ label: t.type.replace('_APP',''), value: t.count }));
    drawBarChart(tData, '#d3-an-types', 'App Type', 'Count', '#ff88aa');

    // 3. Destinations Doughnut
    const destData = [
      { label: 'Broadcast', value: data.destinations.broadcast },
      { label: 'Private', value: data.destinations.private }
    ];
    drawDoughnutChart(destData, '#d3-an-dest', ['#8844ff', '#ffaa00']);

    // 4. Encryption Doughnut
    const encData = [
      { label: 'Plaintext', value: data.plaintext },
      { label: 'Encrypted', value: data.encrypted }
    ];
    drawDoughnutChart(encData, '#d3-an-enc', ['#4488ff', '#f85149']);

    // 5. Top Senders Bubble
    if(data.top_senders) drawBubbleChart(data.top_senders, '#d3-an-senders-bubble', d3.schemeTableau10);

    // 6. Encrypted Senders Bubble
    if(data.encrypted_senders) drawBubbleChart(data.encrypted_senders, '#d3-an-encrypted-senders-bubble', d3.schemeDark2);

    // 7. DM Force Graph
    if(data.top_links) drawForceDirectedGraph(data.top_links, '#d3-an-dm-graph', '#3fb950');

    // 8. Encrypted DM Force Graph
    if(data.encrypted_links) drawForceDirectedGraph(data.encrypted_links, '#d3-an-encrypted-dm-graph', '#f85149');

    // 9. Heatmap
    if (!analyticsHeatmap) {
      analyticsHeatmap = L.map('analytics-heatmap', {zoomControl:true, attributionControl:false})
        .setView([0, 0], 2);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 18}).addTo(analyticsHeatmap);
    }

    // Clear old layers
    analyticsHeatmap.eachLayer(layer => {
      if (layer instanceof L.HeatLayer) {
        analyticsHeatmap.removeLayer(layer);
      }
    });

    const heatPoints = [];
    const bounds = [];
    if (data.top_senders && data.node_positions) {
      data.top_senders.forEach(s => {
        const pos = data.node_positions[s.id];
        if (pos && pos.lat && pos.lon) {
          heatPoints.push([pos.lat, pos.lon, s.count]);
          bounds.push([pos.lat, pos.lon]);
        }
      });
    }

    if (heatPoints.length > 0) {
      L.heatLayer(heatPoints, {radius: 25, blur: 15, maxZoom: 17}).addTo(analyticsHeatmap);
      if (bounds.length > 1) {
        analyticsHeatmap.fitBounds(bounds, {padding: [50, 50]});
      } else if (bounds.length === 1) {
        analyticsHeatmap.setView(bounds[0], 10);
      }
    }

    // Invalidate size in case tab wasn't visible when map was created
    setTimeout(() => { if(analyticsHeatmap) analyticsHeatmap.invalidateSize(); }, 100);

  } catch(e) { console.error('Analytics load error:', e); }
}

"""
    new_content = content[:start_idx] + replace + content[end_idx:]
    with open("templates/index.html", "w") as f:
        f.write(new_content)
    print("Replaced JS successfully")
else:
    print("Could not find start or end index.")
