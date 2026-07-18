import sys
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.brain.sniffer import Sniffer
from app.memory.knowledge_graph import KnowledgeGraph

def run_performance_test():
    print("--- FileFlow V10 Triage Performance Test ---")
    
    sniffer = Sniffer()
    graph = KnowledgeGraph(Path("data/test_knowledge_graph.sqlite"))
    
    # 1. Test Sniffer Speed
    test_cases = [
        (Path("Candidate_CV.pdf"), "This is a Curriculum Vitae with ID 8701015009087"),
        (Path("Invoice_March.pdf"), "TAX INVOICE Total due: R1500"),
        (Path("Z83_Form_Signed.pdf"), "Z83 Application for Employment REF: BH-2024-X"),
        (Path("Unknown_Doc.txt"), "Just some random notes about grocery shopping.")
    ]
    
    start_time = time.perf_counter()
    results = []
    
    for path, text in test_cases:
        result = sniffer.sniff(path, text)
        results.append((path.name, result))
        
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    avg_ms = duration_ms / len(test_cases)
    
    print(f"\n[Sniffer] Processed {len(test_cases)} files in {duration_ms:.2f}ms (Avg: {avg_ms:.2f}ms/file)")
    
    # 2. Test Knowledge Graph Linking
    print("\n[Knowledge Graph] Broadcasting Facts...")
    for filename, result in results:
        if result.confidence > 0.8:
            fake_hash = f"hash_{filename}"
            print(f"  -> Ingesting {filename} ([{result.confidence}] {result.sub_type})")
            graph.ingest_sniff_result(fake_hash, filename, {
                "confidence": result.confidence,
                "category": result.category,
                "sub_type": result.sub_type,
                "facts": result.facts
            })
            
    # 3. Test Retrieval
    print("\n[Knowledge Graph] Testing Cross-Contextual Retrieval...")
    cluster_test = graph.get_related_files("SA_ID", "8701015009087")
    print(f"  -> Found {len(cluster_test)} files linked to SA ID 8701015009087")
    
    print("\nTest completed successfully.")

if __name__ == "__main__":
    run_performance_test()
