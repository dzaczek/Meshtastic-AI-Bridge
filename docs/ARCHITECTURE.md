# Architecture & Message Flows

This document describes the internal architecture of Meshtastic-AI-Bridge v6.0, including all message flows, decision trees, and component interactions.

> All diagrams use [Mermaid](https://mermaid.js.org/) syntax and render natively on GitHub.

---

## System Overview

```mermaid
graph TB
    subgraph External["External Systems"]
        MESH["Meshtastic Device<br/>(LoRa radio)"]
        OAI["OpenAI API<br/>(GPT-4o)"]
        GEM["Google Gemini API"]
        MAT["Matrix Homeserver<br/>(matrix.org)"]
        WEB["Web / DuckDuckGo"]
    end

    subgraph Core["Core Engine"]
        MH["meshtastic_handler.py<br/>Device I/O"]
        MR["message_router.py<br/>Priority Routing"]
        CM["conversation_manager.py<br/>History & Context"]
        CSM["connection_manager.py<br/>State Machine"]
    end

    subgraph Services["Services"]
        AI["ai_bridge.py<br/>LLM Bridge"]
        HB["hal_bot.py<br/>Bot Commands"]
        WA["web_agent.py<br/>Web Scraping"]
        MB["matrix_bridge.py<br/>Matrix Bridge"]
    end

    subgraph UI["User Interface"]
        TUI["tui_app.py<br/>Textual TUI"]
        CLI["main_app.py<br/>Console Mode"]
        MAP["mesh_map.py<br/>OSM Map"]
    end

    MESH <-->|"serial / TCP"| MH
    MH --> MR
    MR --> HB
    MR --> AI
    AI --> OAI
    AI --> GEM
    AI --> WA
    WA --> WEB
    MR --> CM
    MH --- CSM
    MR --> TUI
    MR --> CLI
    TUI --> MAP
    TUI --> MB
    MB <-->|"matrix-nio"| MAT

    style External fill:#1a1a2e,stroke:#30363d,color:#c9d1d9
    style Core fill:#0d1117,stroke:#58a6ff,color:#c9d1d9
    style Services fill:#0d1117,stroke:#3fb950,color:#c9d1d9
    style UI fill:#0d1117,stroke:#d2a8ff,color:#c9d1d9
```

---

## Message Receive Flow

What happens when a LoRa packet arrives from the mesh network.

```mermaid
sequenceDiagram
    participant Radio as Meshtastic Device
    participant MH as meshtastic_handler
    participant TUI as tui_app / main_app
    participant MR as message_router
    participant CM as conversation_manager

    Radio->>MH: pubsub "meshtastic.receive" (packet)
    MH->>MH: Extract sender_id (int → hex)
    MH->>MH: Lookup node in interface.nodes["!hex"]
    MH->>MH: Build name: shortName/longName

    alt TEXT_MESSAGE_APP
        MH->>MH: text = decoded.text
    else PRIVATE_APP
        MH->>MH: text = payload.decode("utf-8")
    end

    MH->>TUI: callback(text, sender_id, sender_name, destination_id, channel_id)
    TUI->>MR: on_message(text, sender_id, sender_name, destination_id, channel_id, ai_node_id)
    MR->>CM: add_message(conversation_id, "user", text)
    MR-->>TUI: RouteResult
    TUI->>TUI: Act on RouteResult (see Priority Routing)
```

---

## Priority Routing

The `message_router.py` evaluates each incoming message against three priority levels. First match wins.

```mermaid
flowchart TD
    MSG["Incoming Message"] --> NORM["Normalize IDs<br/>Detect DM vs Broadcast<br/>Generate conversation_id"]
    NORM --> SAVE["Save to conversation history"]
    SAVE --> P1

    P1{"Priority 1<br/>SOS keywords?"}
    P1 -->|"Yes"| SOS["Broadcast alert on ALL channels<br/>Send confirmation to sender"]
    P1 -->|"No"| P2

    P2{"Priority 2<br/>Bot command?<br/>(!admin, ping, info,<br/>traceroute, qsl, test)"}
    P2 -->|"Yes"| BOT["Execute command<br/>Return response"]
    P2 -->|"No"| P3

    P3{"Priority 3<br/>AI response needed?"}
    P3 --> DM_CHECK{"Is it a DM<br/>to AI node?"}

    DM_CHECK -->|"Yes"| AI_YES["Respond (skip triage)"]
    DM_CHECK -->|"No"| NAME_CHECK{"Bot name<br/>mentioned?"}

    NAME_CHECK -->|"Yes"| AI_YES
    NAME_CHECK -->|"No"| TRIAGE_CHECK{"Triage<br/>enabled?"}

    TRIAGE_CHECK -->|"Yes"| TRIAGE["Call triage AI<br/>(gpt-3.5-turbo)"]
    TRIAGE_CHECK -->|"No"| PROB["Probability check<br/>(default 85%)"]

    TRIAGE -->|"YES"| COOL
    TRIAGE -->|"NO"| SKIP["Skip response"]
    PROB -->|"Pass"| COOL
    PROB -->|"Fail"| SKIP

    COOL{"Cooldown<br/>expired?"}
    COOL -->|"Yes"| AI_YES
    COOL -->|"No"| SKIP

    SOS --> RESULT["RouteResult"]
    BOT --> RESULT
    AI_YES --> RESULT
    SKIP --> RESULT

    style P1 fill:#da3633,stroke:#f85149,color:#fff
    style P2 fill:#1f6feb,stroke:#58a6ff,color:#fff
    style P3 fill:#238636,stroke:#3fb950,color:#fff
    style SOS fill:#da3633,stroke:#f85149,color:#fff
    style BOT fill:#1f6feb,stroke:#58a6ff,color:#fff
    style AI_YES fill:#238636,stroke:#3fb950,color:#fff
```

### RouteResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `reply_text` | `str?` | Direct response (bot command, SOS confirmation) |
| `reply_as_dm` | `bool` | Send reply as DM instead of channel message |
| `reply_channel` | `int` | Channel index for reply |
| `reply_destination` | `str?` | Node ID for DM target |
| `broadcast_alert` | `str?` | SOS alert text to broadcast |
| `broadcast_channels` | `list[int]` | Channels for SOS broadcast |
| `conversation_id` | `str` | Conversation tracking ID |
| `needs_ai_response` | `bool` | Should AI worker be spawned? |
| `skip_triage` | `bool` | Bypass triage (DMs, direct mentions) |
| `handled` | `bool` | Fully processed (no further action needed) |

---

## AI Response Flow

When `needs_ai_response=True`, the UI spawns an `AIProcessingWorker` thread.

```mermaid
sequenceDiagram
    participant TUI as UI Layer
    participant W as AIProcessingWorker
    participant CM as conversation_manager
    participant AI as ai_bridge
    participant LLM as OpenAI / Gemini
    participant WA as web_agent
    participant MH as meshtastic_handler
    participant MB as matrix_bridge

    TUI->>W: spawn thread(text, sender_id, channel, conv_id)

    W->>CM: get_contextual_history(conv_id)
    CM-->>W: context (with summarization if needed)

    opt URL detected in message
        W->>WA: analyze_url_content(url)
        WA-->>W: web_analysis_summary
        W->>CM: add_url_analysis(conv_id, url, summary)
    end

    W->>AI: get_response(history, text, sender_name, node_id)

    alt skip_triage = false
        AI->>LLM: Triage query (should AI respond?)
        LLM-->>AI: YES / NO
    end

    AI->>AI: Build prompt (persona + history + user message)
    AI->>LLM: Generate response
    LLM-->>AI: response text
    AI->>AI: Filter suppressed phrases
    AI-->>W: cleaned response (or None)

    opt Valid response
        W->>W: Apply human-like delay (2-8s)
        W->>CM: add_message(conv_id, "assistant", response)

        alt DM conversation
            W->>MH: send_message(text, destination_id=sender_id)
        else Channel conversation
            W->>MH: send_message(text, channel_index=ch)
        end

        opt Matrix enabled
            W->>MB: send_to_matrix(text, bot_name, sender_id, ...)
        end
    end

    W-->>TUI: update UI (async callback)
```

---

## AI Triage Decision

The triage system uses a lightweight LLM call to decide whether the main AI should respond to a channel message.

```mermaid
flowchart LR
    IN["Channel message<br/>(not DM, not bot-mentioned)"] --> BUILD["Build triage prompt:<br/>- Bot persona (truncated 250 chars)<br/>- Last N channel messages<br/>- Newest message + sender"]

    BUILD --> CALL["Call triage model<br/>(gpt-3.5-turbo, temp=0.0,<br/>max_tokens=5)"]

    CALL --> PARSE{"Response<br/>contains 'YES'?"}

    PARSE -->|"Yes"| RESPOND["Main AI responds"]
    PARSE -->|"No"| SILENT["Stay silent"]

    style IN fill:#0d1117,stroke:#8b949e,color:#c9d1d9
    style CALL fill:#1f6feb,stroke:#58a6ff,color:#fff
    style RESPOND fill:#238636,stroke:#3fb950,color:#fff
    style SILENT fill:#6e7681,stroke:#8b949e,color:#fff
```

---

## Conversation Context Management

How conversation history is stored, loaded, and summarized for AI context.

```mermaid
flowchart TD
    subgraph IDs["Conversation ID Generation"]
        DM_ID["DM: dm_{min(ai_id, user_id)}_{max(ai_id, user_id)}"]
        CH_ID["Channel: ch_{channel_index}_broadcast"]
    end

    subgraph Storage["JSON File Storage"]
        FILE["conversations/{conv_id}.json<br/>[{role, content, timestamp, user_name, node_id}, ...]"]
    end

    subgraph Loading["Context Loading"]
        LOAD["Load full history from JSON"]
        LOAD --> TOK{"Total tokens ><br/>SUMMARIZE_THRESHOLD?"}
        TOK -->|"Yes"| SUM["Summarize old messages<br/>Keep last 3 intact"]
        TOK -->|"No"| CAP
        SUM --> CAP["Cap at MAX_HISTORY_MESSAGES"]
        CAP --> OUT["Return context array<br/>for LLM prompt"]
    end

    IDs --> FILE
    FILE --> LOAD
```

---

## SOS / Emergency Flow

Emergency messages bypass all normal routing and broadcast on every active channel.

```mermaid
sequenceDiagram
    participant User as Mesh Node
    participant MR as message_router
    participant MH as meshtastic_handler
    participant TUI as UI Layer

    User->>MR: "SOS we need help!"

    Note over MR: Keyword match:<br/>"sos", "help", "pomoc", "mayday",<br/>"emergency", "ratunku", "hilfe",<br/>"rescue", "alarm", "danger", ...

    MR->>MR: Build alert:<br/>"[SOS] ALERT from Name (!id): SOS we need help!"
    MR->>MR: Get ALL active channel indices

    MR-->>TUI: RouteResult(broadcast_alert=..., broadcast_channels=[0,1,2,...])

    loop Each channel
        TUI->>MH: send_message(alert, channel_index=ch)
        MH->>User: LoRa broadcast on channel
    end

    TUI->>MH: send_message(confirmation, destination=sender)
    Note over TUI: "Your distress message has been<br/>broadcast on N channel(s)."
```

---

## Bot Command Flow

Commands handled by `hal_bot.py`. Two categories: network commands (anyone) and admin commands (authorized nodes only).

```mermaid
flowchart TD
    MSG["Incoming message"] --> DETECT{"Starts with<br/>'!admin'?"}

    DETECT -->|"Yes"| AUTH{"sender_id in<br/>ADMIN_NODE_IDS?"}
    DETECT -->|"No"| CMD{"Match command?<br/>(ping, info, test,<br/>qsl, traceroute)"}

    AUTH -->|"No"| DENY["Unauthorized"]
    AUTH -->|"Yes"| ADMIN

    subgraph ADMIN["Admin Commands"]
        A1["!admin status<br/>Connection, nodes, AI service, uptime"]
        A2["!admin nodes<br/>List first 15 nodes"]
        A3["!admin channels<br/>List active channels"]
        A4["!admin persona &lt;text&gt;<br/>Update AI personality"]
        A5["!admin switch_ai &lt;service&gt;<br/>Switch OpenAI / Gemini"]
    end

    CMD -->|"Yes"| NETCMD

    subgraph NETCMD["Network Commands"]
        direction TB
        N_LOOKUP["Lookup sender node info:<br/>name, RSSI, SNR, hops,<br/>battery, connection type"]

        N_LOOKUP --> N1["ping / qsl<br/>Signal report + connection info"]
        N_LOOKUP --> N2["info / test<br/>Node status summary"]
        N_LOOKUP --> N3["traceroute<br/>Start async route trace"]
    end

    CMD -->|"No"| PASS["Not a command<br/>→ continue to AI routing"]

    N3 --> TRACE_BG["Background thread:<br/>Wait 30s, collect route,<br/>send result to mesh"]

    style ADMIN fill:#1f6feb,stroke:#58a6ff,color:#fff
    style NETCMD fill:#238636,stroke:#3fb950,color:#fff
    style DENY fill:#da3633,stroke:#f85149,color:#fff
```

---

## Matrix Bridge Flow

Bidirectional bridge between mesh channels/DMs and Matrix rooms.

```mermaid
flowchart TD
    subgraph MeshToMatrix["Mesh → Matrix"]
        M_IN["Mesh message received"] --> M_FMT["Format:<br/>**shortName/longName** (!nodeId): text"]
        M_FMT --> M_ROOM{"Is DM?"}
        M_ROOM -->|"Yes"| M_DM["Get/create room:<br/>#mesh-dm-{nodeId}"]
        M_ROOM -->|"No"| M_CH["Get/create room:<br/>#mesh-ch{index}"]
        M_DM --> M_SEND["room_send() via matrix-nio"]
        M_CH --> M_SEND
        M_SEND --> M_INV["Auto-invite configured users"]
    end

    subgraph MatrixToMesh["Matrix → Mesh"]
        X_IN["Matrix message event"] --> X_FILTER{"Own message?<br/>Old message?"}
        X_FILTER -->|"Skip"| X_DROP["Ignore"]
        X_FILTER -->|"Process"| X_MAP["Map room → channel/node"]
        X_MAP --> X_FMT["Format:<br/>[matrixUser] text<br/>(cap 194 chars)"]
        X_FMT --> X_TYPE{"Room type?"}
        X_TYPE -->|"DM room"| X_DM["send_message(<br/>destination=nodeId)"]
        X_TYPE -->|"Channel room"| X_CH["send_message(<br/>channel_index=ch)"]
    end

    style MeshToMatrix fill:#0d1117,stroke:#58a6ff,color:#c9d1d9
    style MatrixToMesh fill:#0d1117,stroke:#3fb950,color:#c9d1d9
```

### Matrix Room Mapping

```mermaid
graph LR
    subgraph Mesh["Mesh Network"]
        CH0["Channel 0 (default)"]
        CH1["Channel 1"]
        CH2["Channel 2"]
        DM1["DM from node abc123"]
        DM2["DM from node def456"]
    end

    subgraph Matrix["Matrix Rooms"]
        R0["#mesh-ch0:matrix.org"]
        R1["#mesh-ch1:matrix.org"]
        R2["#mesh-ch2:matrix.org"]
        RD1["#mesh-dm-abc123:matrix.org"]
        RD2["#mesh-dm-def456:matrix.org"]
    end

    CH0 <--> R0
    CH1 <--> R1
    CH2 <--> R2
    DM1 <--> RD1
    DM2 <--> RD2
```

---

## Web Agent Flow

How the AI handles URLs and web queries.

```mermaid
flowchart TD
    TRIGGER{"URL in message?<br/>or web query?"} -->|"URL"| URL_PATH
    TRIGGER -->|"Query"| QUERY_PATH

    subgraph URL_PATH["URL Analysis"]
        U1["Detect URL via regex"] --> U2["Screenshot page<br/>(Playwright / Chromium)"]
        U2 --> U3["Extract text content"]
        U3 --> U4["Vision model analysis<br/>(gpt-4-vision)"]
        U4 --> U5["Save analysis to<br/>conversation history"]
        U5 --> U6["Include in AI context"]
    end

    subgraph QUERY_PATH["Web Query Pipeline"]
        Q1["Analyze query intent<br/>(OpenAI)"] --> Q2["Execute search<br/>(DuckDuckGo → Google fallback)"]
        Q2 --> Q3["Extract page content<br/>(CSS selectors)"]
        Q3 --> Q4["Generate response<br/>via OpenAI"]
    end

    subgraph WEATHER["Weather Shortcut"]
        W1["Try Google weather URL"]
        W1 --> W2["Regex extract<br/>temperature + condition"]
    end
```

---

## Connection State Machine

Managed by `connection_manager.py`, handles reconnection with exponential backoff.

```mermaid
stateDiagram-v2
    [*] --> DISCONNECTED

    DISCONNECTED --> CONNECTING : start_connection()

    CONNECTING --> CONNECTED : connection_succeeded()
    CONNECTING --> RECONNECTING : connection_failed()

    CONNECTED --> RECONNECTING : health check failed<br/>(3 consecutive failures)
    CONNECTED --> SHUTTING_DOWN : shutdown()

    RECONNECTING --> CONNECTED : connection_succeeded()
    RECONNECTING --> FAILED : max retries exceeded

    FAILED --> RECONNECTING : manual retry
    FAILED --> SHUTTING_DOWN : shutdown()

    SHUTTING_DOWN --> DISCONNECTED : cleanup complete
    DISCONNECTED --> [*]

    note right of RECONNECTING
        Exponential backoff:
        delay = base * 2^retry
        Max delay: 30s
        Jitter: +/- 20%
    end note

    note right of CONNECTED
        Monitor thread checks
        health every 30s.
        update_activity() called
        on each received packet.
    end note
```

---

## Full Message Lifecycle (End-to-End)

A complete view: from LoRa radio to AI response, Matrix forwarding, and back.

```mermaid
sequenceDiagram
    actor User as Mesh User
    participant Radio as LoRa Radio
    participant MH as meshtastic_handler
    participant TUI as tui_app
    participant MR as message_router
    participant CM as conversation_manager
    participant HB as hal_bot
    participant AI as ai_bridge
    participant LLM as OpenAI / Gemini
    participant MB as matrix_bridge
    participant MAT as Matrix Room

    User->>Radio: Send message
    Radio->>MH: packet (pubsub)
    MH->>MH: Parse packet, resolve node name
    MH->>TUI: callback(text, sender, dest, channel)

    TUI->>MR: on_message(...)
    MR->>CM: Save incoming message

    alt SOS keyword detected
        MR-->>TUI: RouteResult(broadcast_alert)
        TUI->>Radio: Broadcast on all channels
    else Bot command
        MR->>HB: handle_command(text, sender)
        HB-->>MR: response
        MR-->>TUI: RouteResult(reply_text)
        TUI->>Radio: Send reply
    else AI response needed
        MR-->>TUI: RouteResult(needs_ai_response=true)
        TUI->>TUI: Spawn AIProcessingWorker

        TUI->>CM: get_contextual_history()
        CM-->>TUI: context
        TUI->>AI: get_response(context, text)
        AI->>LLM: Prompt with persona + context
        LLM-->>AI: response
        AI-->>TUI: cleaned response

        TUI->>Radio: Send response to mesh
    end

    opt Matrix enabled
        TUI->>MB: send_to_matrix(text, sender_name, ...)
        MB->>MAT: room_send()
    end

    opt Matrix user replies
        MAT->>MB: on_matrix_event(room, text)
        MB->>MH: send_message(text, channel/dest)
        MH->>Radio: Transmit to mesh
    end
```

---

## Module Dependency Map

```mermaid
graph TD
    CONFIG["config.py<br/>.env"] --> MH
    CONFIG --> AI
    CONFIG --> HB
    CONFIG --> MR
    CONFIG --> MB

    MH["meshtastic_handler.py"]
    CSM["connection_manager.py"]
    MR["message_router.py"]
    CM["conversation_manager.py"]
    AI["ai_bridge.py"]
    HB["hal_bot.py"]
    WA["web_agent.py"]
    MB["matrix_bridge.py"]
    TUI["tui_app.py"]
    CLI["main_app.py"]
    MAP["mesh_map.py"]

    MH --> CSM
    TUI --> MH
    TUI --> MR
    TUI --> MB
    TUI --> MAP
    CLI --> MH
    CLI --> MR

    MR --> CM
    MR --> HB
    MR --> AI

    AI --> WA

    HB --> MH

    MB --> MH

    style CONFIG fill:#d29922,stroke:#e3b341,color:#0d1117
    style TUI fill:#d2a8ff,stroke:#bc8cff,color:#0d1117
    style CLI fill:#d2a8ff,stroke:#bc8cff,color:#0d1117
    style MR fill:#58a6ff,stroke:#388bfd,color:#0d1117
```

---

## Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `MESHTASTIC_CONNECTION_TYPE` | `"serial"` | `"serial"` or `"tcp"` |
| `MESHTASTIC_DEVICE_SPECIFIER` | `None` | Device path or IP address |
| `DEFAULT_AI_SERVICE` | `"openai"` | `"openai"` or `"gemini"` |
| `OPENAI_MODEL_NAME` | `"gpt-4o"` | Main AI model |
| `AI_RESPONSE_PROBABILITY` | `0.85` | Chance of responding (0.0 - 1.0) |
| `AI_MIN_RESPONSE_DELAY_S` | `2` | Minimum delay before response |
| `AI_MAX_RESPONSE_DELAY_S` | `8` | Maximum delay before response |
| `AI_RESPONSE_COOLDOWN_S` | `60` | Per-conversation cooldown |
| `ENABLE_AI_TRIAGE_ON_CHANNELS` | `False` | Use triage AI for channel messages |
| `TRIAGE_AI_MODEL_NAME` | `"gpt-3.5-turbo"` | Model for triage decisions |
| `MAX_HISTORY_MESSAGES_FOR_CONTEXT` | `10` | Max messages in AI context |
| `SUMMARIZE_THRESHOLD_TOKENS` | `1000` | Token threshold for summarization |
| `MATRIX_ENABLED` | `False` | Enable Matrix bridge |
| `MATRIX_HOMESERVER` | `"https://matrix.org"` | Matrix server URL |
| `MATRIX_ROOM_PREFIX` | `"mesh"` | Prefix for room aliases |
| `MATRIX_INVITE_USERS` | `[]` | Auto-invite these Matrix users |
| `ADMIN_NODE_IDS` | `[]` | Hex node IDs for admin access |
| `BOT_NAME` | `"Eva"` | Bot display name |
