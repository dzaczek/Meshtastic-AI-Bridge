with open("templates/index.html", "r") as f:
    content = f.read()

search = "</head>"
replace = """  <script src="https://d3js.org/d3.v7.min.js"></script>
  <script src="https://leaflet.github.io/Leaflet.heat/dist/leaflet-heat.js"></script>
</head>"""

if search in content:
    with open("templates/index.html", "w") as f:
        f.write(content.replace(search, replace))
    print("Replaced head successfully")
else:
    print("Not found")
