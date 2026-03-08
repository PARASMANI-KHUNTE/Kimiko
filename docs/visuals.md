# 📊 Kimiko Visualizations

This document provides visual representations of Kimiko's internal logic, architecture, and memory systems.

## 1. System Overview (High-Level Flow)

The following diagram shows how a request travels from the user through the multimodal layers to the final response.

```mermaid
graph TD
    A[User Request] --> B{Modality?}
    B -- Voice --> C[Whisper STT]
    B -- Image --> D[Vision Engine]
    B -- Text --> E[Intent Classifier]
    
    C --> E
    D --> E
    
    E --> F[Retrieval Engine]
    
    subgraph MemoryLayer [Memory & RAG]
        F --> G[(PostgreSQL Facts)]
        F --> H[(Qdrant Semantic)]
        F --> I[Redis History]
    end
    
    G & H & I --> J[Context Builder]
    J --> K[Model Router]
    
    subgraph Inference [Hybrid Routing]
        K -- Critical/Private --> L[Local Ollama]
        K -- Complex/Heavy --> M[Remote API]
    end
    
    L & M --> N[LangGraph Agent]
    
    subgraph AgentLoop [ReAct Loop]
        N --> O{Need Tool?}
        O -- Yes --> P[Tool Executor]
        P --> Q[Internal Tools / Plugins]
        Q --> N
        O -- No --> R[Final Answer]
    end
    
    R --> S[Streaming Engine]
    S --> T[User Response]
```

---

## 2. Hybrid Memory Logic

Kimiko's memory mimics human recall: immediate history for context, semantic search for associations, and structured facts for identity.

```mermaid
mindmap
  root((Kimiko Memory))
    Short Term
      ::icon(fa fa-clock)
      Recent Messages
      Immediate Session Context
      RAM/Redis
    Middle Term
      ::icon(fa fa-search)
      Semantic RAG
      Qdrant Vector DB
      Document Ingestion
    Long Term
      ::icon(fa fa-brain)
      User Facts
      Identity & Preferences
      PostgreSQL
      Fact Decay Engine
```

---

## 3. Fact Evolution Cycle

How Kimiko learns and reinforces knowledge about the user.

```mermaid
sequenceDiagram
    participant U as User
    participant W as Fact Worker
    participant DB as SQL Fact Store
    participant R as Retrieval
    
    U->>W: "My favorite language is Python"
    W->>W: Extract: (category=preference, fact=Python, confidence=0.8)
    W->>DB: Store/Update Fact
    loop Every 24 hours
        DB->>DB: Apply Exponential Decay
    end
    Note over DB: Confidence scores fade over time
    U->>R: "What language do I like?"
    R->>DB: Get Facts (Filter by user_id)
    DB->>R: Returns High Confidence Facts
    R->>U: "You like Python"
    Note right of U: Reinforcement resets decay
```

---

## 4. Plugin Ecosystem

Kimiko's extensibility model.

```mermaid
flowchart LR
    subgraph Core
        O[Orchestrator]
        TR[Tool Registry]
    end
    
    subgraph PluginsDir [src/kimiko/plugins/installed/]
        P1[Weather Plugin]
        P2[Custom Plugin]
    end
    
    PM[Plugin Manager] -- Scans --> PluginsDir
    PM -- Instantiates --> P1
    PM -- Registers Tools --> TR
    
    TR -- Namespaced Tool --> OA[Agent]
    Note over TR: weather.get_current<br/>custom.my_tool
```
