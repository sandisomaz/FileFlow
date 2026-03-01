# Architecture Sketch: The "Stories" Engine

This diagram visualizes how FileFlow X moves beyond folders into **Relational Stories**.

```mermaid
graph TD
    subgraph "Raw Data Points (The Mess)"
        F1["IMG_9821.jpg (ID Document)"]
        F2["Draft_v1.docx (Legal Research)"]
        F3["Email_Archive.pst (Recruiter Thread)"]
        F4["Z83_Form.pdf (Application)"]
        F5["Movie_Matrix.mkv (Watching)"]
    end

    subgraph "The Intelligence Mesh (FileFlow X)"
        Stream[StreamUnpacker] -->|Yields| Judge[AI Judge Pool]
        Judge -->|Extracts Metadata| KG[(Knowledge Graph)]
        KG -->|Links by CaseID| Story1
        KG -->|Links by Creation Burst| Story2
        KG -->|Links by Category| Story3
    end

    subgraph "The Human Layer (Stories)"
        Story1["Story: DPSA Application 2024"]
        Story2["Story: Late Night LLB Research"]
        Story3["Story: Personal Entertainment"]
    end

    F4 -.-> Story1
    F1 -.-> Story1
    F3 -.-> Story1
    
    F2 -.-> Story2
    
    F5 -.-> Story3

    style Story1 fill:#f9f,stroke:#333,stroke-width:4px
    style Story2 fill:#bbf,stroke:#333,stroke-width:2px
    style Story3 fill:#dfd,stroke:#333,stroke-width:2px
```

### 🗝️ Core Logic of a "Story"
1. **Shared Metadata**: A Case ID or Phone Number appearing in a PDF and an Image links them instantly.
2. **Temporal Proximity**: If you save 5 files within 10 minutes, they are likely related to the same "task" (e.g., preparing for an interview).
3. **Semantic Similarity**: The "vibe" of the text (e.g., "POPIA Compliance") groups files even if they don't share keywords.
