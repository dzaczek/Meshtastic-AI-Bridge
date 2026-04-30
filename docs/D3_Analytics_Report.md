# Analiza i Architektura Wizualizacji Danych z Sieci Meshtastic (D3.js)

Jako Data Visualization Engineer przeanalizowałem strukturę bazy danych (`node_db.py`) oraz specyfikę działania Meshtastic. Sieci mesh (LoRa) charakteryzują się rzadkim próbkowaniem danych, utratą pakietów (packet loss), zmienną jakością sygnału i dużą asymetrią ruchu (niewielki ruch prywatny, dużo broadcastów, beaconów GPS i telemetrii). Poniżej znajduje się kompleksowa propozycja rozwiązania opartego na D3.js.

## 1. Analiza Struktury Danych i Pola Analityczne

W oparciu o schemat w `node_db.py`, dane można podzielić na następujące kluczowe obszary i pola:

### Najważniejsze Pola Analityczne (Źródła dla D3):
1.  **Topologia i Ruch Sieciowy (`packets`, `traceroutes`)**
    *   `ts` (timestamp) – absolutna podstawa do analizy szeregów czasowych.
    *   `from_id`, `to_id` – definicja krawędzi w grafach połączeń. Wartość `broadcast` lub `ffffffff` identyfikuje ruch ogólny.
    *   `portnum` (typ pakietu np. TEXT, POSITION, TELEMETRY) – pozwala kategoryzować użycie sieci.
    *   `hops` / `route_json` (z `traceroutes`) – ścieżki i długość tras, krytyczne dla oceny sprawności routingu.
2.  **Jakość Sygnału RF (`signal_history`, parametry w `traceroutes`)**
    *   `snr` (Signal-to-Noise Ratio) – najważniejszy wskaźnik jakości linku.
    *   `rssi` (Received Signal Strength Indicator) – natężenie sygnału.
3.  **Węzły i Infrastruktura (`nodes`, `telemetry_history`, `position_history`)**
    *   `lat`, `lon` – geoprzestrzenna dystrybucja sieci.
    *   `battery`, `voltage` – kondycja zasilania węzłów, kluczowa dla urządzeń zasilanych solarnie.
    *   `ch_util` (Channel Utilization) – wskaźnik przeciążenia pasma radiowego przez dany węzeł.
    *   `via_mqtt` – flaga pozwala odróżnić lokalny ruch RF od globalnego ruchu internetowego.

## 2. Propozycja Dodatkowych Metryk

Aby stworzyć zaawansowany dashboard, surowe dane to za mało. Należy obliczyć pochodne KPI po stronie backendu lub w pamięci przeglądarki (D3.js/Crossfilter):

1.  **Network Centrality (Centralność węzłów):** Jak często dany węzeł występuje jako przekaźnik w `route_json` (Traceroutes). Pozwala zidentyfikować „wąskie gardła” (bottlenecks) lub najważniejsze bramki (gateways).
2.  **Packet Delivery Ratio (PDR) / Opadanie Sygnału:** Różnica między wysłanymi a odebranymi pakietami na hopach. Można oszacować z brakujących sekwencji, ale w tej bazie lepszym proxy będzie **korelacja hopów i SNR**.
3.  **Radio vs MQTT Ratio:** Jak duży % ruchu pochodzi z internetu (MQTT) względem prawdziwego radia (LORA).
4.  **Uptime / Battery Degradation Rate:** Zmiana `voltage` lub `battery` w czasie (delta %). Pozwala przewidzieć śmierć węzła (wyłączenie).
5.  **Bandwidth Congestion Risk:** Połączenie średniego SNR ze średnim `ch_util`. Węzły z wysokim `ch_util` (>30%) i słabym powiązaniem tworzą „chokepoints”.

## 3. Zestaw Wykresów i Wizualizacji D3.js

Biorąc pod uwagę specyfikę (nawet kilkadziesiąt tysięcy pakietów dziennie) podejście musi być hybrydowe (SVG + Canvas).

| Wykres / Komponent | Opis i Problem, który rozwiązuje | Dane wejściowe | Interakcje | Technologia (D3) |
| :--- | :--- | :--- | :--- | :--- |
| **Node Network Graph** | Pokazuje topologię sieci. Identyfikuje węzły centralne i odizolowane grupy (island networks). | `packets` (agregowane do linków: `from`->`to`, weight: `count`), status online z `nodes`. | Zoom/Pan, najechanie podświetla sąsiadów węzła i ich powiązania (Edge Bundling). | **Canvas + SVG (Hybryda)**. Symulacja D3 Force (Canvas) + Tooltipy (SVG/HTML). Przy >500 węzłach SVG renderuje się za wolno. |
| **Activity Timeline (Brushable)** | Kontekst czasowy. Kiedy sieć „śpi”, a kiedy ma piki (np. anomalia propagacji). Służy też jako globalny filtr czasu. | Aggregacja `ts` -> ilosc pakietów na godzinę. | Brush (selekcja okna czasowego) filtrujący inne wykresy. | **SVG** (obszary liniowe D3.area). |
| **Geospatial Map** | Nakładka na mapę Leaflet z użyciem D3 do renderowania wektorów siły sygnału lub Heatmapy aktywności RF. | `position_history` (`lat`,`lon`) + `packets` density. | Leaflet pan/zoom -> D3 update. Hover na hexagonie. | **Canvas** (dla heatmapy Leaflet) lub **SVG Layer** (D3 Hexbin / markery). |
| **SNR / Distance Scatter** | Korelacja jakości sygnału (SNR) od dystansu geograficznego. Pokazuje wydajność anten (odstępstwa od modelu). | Połączone pozycje z `traceroutes` (haversine dist) i `snr_towards`. | Click by odfiltrować tylko konkretny hw_model (sprzęt). | **Canvas/SVG**. Dla tysięcy punktów użyć `d3.hexbin`. |
| **Battery Life Decay Curve** | Wykres liniowy przewidujący wyczerpanie baterii. Rozwiązuje problem "Kiedy muszę iść wymienić Powerbank/Baterię słoneczną?". | Szereg czasowy `telemetry_history` (`ts`, `voltage`/`battery`). | Oś X (czas), Hover dla odczytu wartości. | **SVG** (d3.line z interpolacją). |
| **Sankey Diagram (Trasy)** | Jak płyną pakiety. Wizualizuje `route_json` z traceroute. Gdzie najczęściej "skaczą" pakiety. | Agregowane trasy (Node A -> Node B -> Node C). | Podświetlanie ścieżek "flow". | **SVG** (d3-sankey). |
| **Channel Utilization Joyplot (Ridgeline)** | Zamiast nudnych linii, zestaw nałożonych dystrybucji `ch_util` dla głównych routerów. | `telemetry_history` (rozkład w przedziałach). | -- | **SVG** |

## 4. Architektura Dashboardu i Poziomy Zaawansowania

Dashboard powinien korzystać z wzorca **Crossfilter + D3**, lub stanu komponentowego (np. React + D3, bądź lekki Vanilla JS observer pattern), gdzie wybór czasu na Timeline filtruje Mapę i Graf.

### Warianty:
*   **Prosty (Statyczny / Podsumowanie):** Oparty tylko na SVG. Wykresy słupkowe zliczeń (Typy Pakietów), proste linie SNR i baterii per węzeł. Dobre na widok mobilny.
*   **Średniozaawansowany (Dashboard operatorski):** Zawiera szczotkowanie (Brush & Zoom) na osi czasu. Dodaje SVG Force Graph. Dobry do lokalnej analizy bazy danych SQLite dla mniejszej grupy węzłów (< 200).
*   **Zaawansowany (Live Mesh Ops Center):** WebSockets dla "Live data". Canvas Force Graph z tysiącami linków. D3.hexbin. Dedykowany Web Worker przeliczający układ grafu sił (Force layout), by nie blokować UI. Leaflet połączony z D3 do overlayów tras sygnału.

### Filtrowanie i Skalowanie
Zastosuj technikę *Data Decimation/Downsampling* na backendzie lub przesyłaj pule zagregowane. Przekazanie przeglądarce miliona rekordów `snr` zawiesi kartę.

### Prywatność i Bezpieczeństwo
*   Lokalizacje GPS prywatnych węzłów mogą być rozmywane (Geo-jittering: dodawanie szumu losowego +/- 0.005 stopnia).
*   Możliwość pseudonimizacji `node_id` (np. hashowanie MAC / ID), aby nie wystawiać prawdziwych numerów urządzeń publicznie.

## 5. Przykładowy Nowoczesny Kod D3.js (ES6 Modules)

Oto koncepcja "Zaawansowanego" Grafu Połączeń z wykorzystaniem hybrydy (Siły obliczane na danych bez DOM, render w Canvas) dla wysokiej wydajności (kod jako szkic architektoniczny):

```javascript
// src/components/MeshForceGraph.js
import * as d3 from 'd3';

export class MeshForceGraph {
  constructor(containerId, data) {
    this.container = document.querySelector(containerId);
    this.width = this.container.clientWidth;
    this.height = this.container.clientHeight;

    // Canvas setup for performance (10k+ edges)
    this.canvas = d3.select(containerId)
      .append('canvas')
      .attr('width', this.width)
      .attr('height', this.height);
    this.ctx = this.canvas.node().getContext('2d');

    // SVG setup for interactive elements (tooltips, invisible hitboxes if needed)
    this.svg = d3.select(containerId)
      .append('svg')
      .style('position', 'absolute')
      .style('top', 0).style('left', 0)
      .attr('width', this.width)
      .attr('height', this.height);

    this.nodes = data.nodes;
    this.links = data.links;
    this.initSimulation();
  }

  initSimulation() {
    this.simulation = d3.forceSimulation(this.nodes)
      .force('link', d3.forceLink(this.links).id(d => d.id).distance(50))
      .force('charge', d3.forceManyBody().strength(-150))
      .force('center', d3.forceCenter(this.width / 2, this.height / 2))
      // Zapobiega pokrywaniu się punktów
      .force('collide', d3.forceCollide().radius(d => this.getNodeRadius(d) + 2))
      .on('tick', () => this.drawCanvas());

    // Zoom and pan
    this.transform = d3.zoomIdentity;
    d3.select(this.canvas.node()).call(d3.zoom()
      .scaleExtent([0.1, 8])
      .on('zoom', (e) => {
        this.transform = e.transform;
        this.drawCanvas();
      }));
  }

  getNodeRadius(node) {
    // Węzły z dużą ilością wiadomości są większe
    return Math.max(3, Math.min(15, Math.sqrt(node.packetCount || 0)));
  }

  drawCanvas() {
    this.ctx.save();
    this.ctx.clearRect(0, 0, this.width, this.height);
    this.ctx.translate(this.transform.x, this.transform.y);
    this.ctx.scale(this.transform.k, this.transform.k);

    // Rysowanie krawędzi (Links)
    this.ctx.beginPath();
    this.links.forEach(link => {
      this.ctx.moveTo(link.source.x, link.source.y);
      this.ctx.lineTo(link.target.x, link.target.y);
    });
    this.ctx.strokeStyle = 'rgba(120, 180, 220, 0.15)'; // Meshtastic UI border color
    this.ctx.lineWidth = 1 / this.transform.k; // Zawsze 1px niezależnie od zoomu
    this.ctx.stroke();

    // Rysowanie węzłów (Nodes)
    this.nodes.forEach(node => {
      this.ctx.beginPath();
      this.ctx.moveTo(node.x + 5, node.y);
      this.ctx.arc(node.x, node.y, this.getNodeRadius(node), 0, 2 * Math.PI);
      // Koloryzacja (Radio = zielony, MQTT = pomarańczowy, OFFLINE = szary)
      if (!node.isOnline) {
         this.ctx.fillStyle = '#555555';
      } else if (node.viaMqtt) {
         this.ctx.fillStyle = '#f0883e';
      } else {
         this.ctx.fillStyle = '#4dffd1'; // Meshtastic brand color
      }
      this.ctx.fill();
    });
    this.ctx.restore();
  }
}
```

Powyższy kod rozwiązuje krytyczny problem sieci Meshtastic – SVG dławi się przy wielu elementach grafu sił (zwłaszcza podczas update'ów), a renderowanie w obiekcie `<canvas>` pozwala na płynną symulację fizyki dla tysięcy odbitych pakietów i traceroute'ów w czasie rzeczywistym.
