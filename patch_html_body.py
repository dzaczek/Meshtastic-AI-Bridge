with open("templates/index.html", "r") as f:
    content = f.read()

search = """<!-- ══════════════════════════════════════════════════════════════
     ANALYTICS TAB
════════════════════════════════════════════════════════════════ -->
<div id="tab-analytics" class="tab-pane" style="flex-direction:column; padding: 15px; overflow-y:auto; gap: 15px;">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <h2 style="color:var(--text); margin:0;">Packet Analytics</h2>
    <div style="font-size:0.8em; color:var(--muted);">
      <select id="analytics-days" onchange="initAnalytics()" style="background:var(--surf); color:var(--text); border:1px solid var(--border); padding:4px;">
        <option value="1">Last 24 Hours</option>
        <option value="7" selected>Last 7 Days</option>
        <option value="30">Last 30 Days</option>
      </select>
    </div>
  </div>

  <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:15px;">

    <!-- Top row -->
    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md);">
      <div class="stat-title">Hourly Activity</div>
      <div style="height:150px; position:relative;"><canvas id="chart-an-hourly"></canvas></div>
    </div>

    <!-- Middle row charts -->
    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md);">
      <div class="stat-title">Top Senders</div>
      <div style="height:150px; position:relative;"><canvas id="chart-an-senders"></canvas></div>
    </div>

    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md);">
      <div class="stat-title">Top App Types</div>
      <div style="height:150px; position:relative;"><canvas id="chart-an-types"></canvas></div>
    </div>

  </div>

  <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:15px;">
    <!-- Bottom row charts -->
    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md); display:flex; align-items:center;">
      <div style="flex:1;">
          <div class="stat-title">Destinations</div>
          <div style="height:130px; position:relative;"><canvas id="chart-an-dest"></canvas></div>
      </div>
      <div style="flex:1;">
          <div class="stat-title">Encryption</div>
          <div style="height:130px; position:relative;"><canvas id="chart-an-enc"></canvas></div>
      </div>
    </div>

    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md);">
      <div class="stat-title">Top Links (From -> To)</div>
      <div id="analytics-links-list" style="font-family:var(--font-mono); font-size:0.75em; margin-top:10px;"></div>
    </div>

  </div>
</div>"""

replace = """<!-- ══════════════════════════════════════════════════════════════
     ANALYTICS TAB
════════════════════════════════════════════════════════════════ -->
<div id="tab-analytics" class="tab-pane" style="flex-direction:column; padding: 15px; overflow-y:auto; gap: 15px;">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <h2 style="color:var(--text); margin:0;">Packet Analytics</h2>
    <div style="font-size:0.8em; color:var(--muted);">
      <select id="analytics-days" onchange="initAnalytics()" style="background:var(--surf); color:var(--text); border:1px solid var(--border); padding:4px;">
        <option value="1">Last 24 Hours</option>
        <option value="7" selected>Last 7 Days</option>
        <option value="30">Last 30 Days</option>
      </select>
    </div>
  </div>

  <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:15px;">

    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md);">
      <div class="stat-title">Hourly Activity</div>
      <div id="d3-an-hourly" style="height:150px; position:relative;"></div>
    </div>

    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md);">
      <div class="stat-title">Top App Types</div>
      <div id="d3-an-types" style="height:150px; position:relative;"></div>
    </div>

    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md); display:flex; align-items:center;">
      <div style="flex:1;">
          <div class="stat-title">Destinations</div>
          <div id="d3-an-dest" style="height:130px; position:relative;"></div>
      </div>
      <div style="flex:1;">
          <div class="stat-title">Encryption</div>
          <div id="d3-an-enc" style="height:130px; position:relative;"></div>
      </div>
    </div>

  </div>

  <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(400px, 1fr)); gap:15px;">

    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md);">
      <div class="stat-title">Top Senders (Bubble Chart)</div>
      <div id="d3-an-senders-bubble" style="height:350px; position:relative; overflow:hidden;"></div>
    </div>

    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md);">
      <div class="stat-title">Encrypted Senders (Bubble Chart)</div>
      <div id="d3-an-encrypted-senders-bubble" style="height:350px; position:relative; overflow:hidden;"></div>
    </div>

    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md);">
      <div class="stat-title">Direct Messages (Force-Directed Graph)</div>
      <div id="d3-an-dm-graph" style="height:350px; position:relative; overflow:hidden;"></div>
    </div>

    <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md);">
      <div class="stat-title">Encrypted Direct Messages (Force-Directed Graph)</div>
      <div id="d3-an-encrypted-dm-graph" style="height:350px; position:relative; overflow:hidden;"></div>
    </div>

  </div>

  <div class="stat-block" style="background:var(--surf2); border:1px solid var(--border); padding:12px; border-radius:var(--r-md);">
    <div class="stat-title">Most Talkative Nodes (Heatmap)</div>
    <div id="analytics-heatmap" style="height:400px; border-radius:var(--r-md); border:1px solid var(--border-s); position:relative; z-index:0;"></div>
  </div>

</div>"""

if search in content:
    with open("templates/index.html", "w") as f:
        f.write(content.replace(search, replace))
    print("Replaced body successfully")
else:
    print("Not found")
