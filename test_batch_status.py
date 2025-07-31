#!/usr/bin/env python3
"""
Quick test for the batch processor status display
"""

from batch_processor import BatchProcessor

def test_batch_processor_status():
    """Test the batch processor status display"""
    print("🧪 TESTING BATCH PROCESSOR STATUS DISPLAY")
    print("=" * 50)
    
    try:
        bp = BatchProcessor()
        
        # Get the status summary
        summary = bp.url_manager.get_status_summary()
        
        print("📊 STATUT DES VIDÉOS")
        print("Résumé des statuts:")
        for status, count in summary.items():
            print(f"  {status}: {count} vidéos")
        
        # Show detailed status with channels  
        bp.show_detailed_status_with_channels()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_batch_processor_status()
