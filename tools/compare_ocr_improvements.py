"""
Compare original vs improved OCR results
Generate improvement metrics for each protocol
"""
import json
import os
from database import get_session
from models import Meeting, Discussion

def load_ocr_results(meeting_id, version='original'):
    """Load OCR results from JSON file"""
    if version == 'improved':
        # Improved files are in current directory
        filename = f"protocol_ocr_analysis_{meeting_id}_improved.json"
    else:
        # Original files might be in ocr_results/ subdirectory or current directory
        filename_ocr_results = f"ocr_results/protocol_ocr_analysis_{meeting_id}.json"
        filename_current = f"protocol_ocr_analysis_{meeting_id}.json"

        if os.path.exists(filename_ocr_results):
            filename = filename_ocr_results
        elif os.path.exists(filename_current):
            filename = filename_current
        else:
            print(f"Warning: protocol_ocr_analysis_{meeting_id}.json not found in ocr_results/ or current directory")
            return None

        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)

    if not os.path.exists(filename):
        print(f"Warning: {filename} not found")
        return None

    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_db_stats(meeting_id):
    """Get actual database statistics for comparison"""
    session = get_session()

    meeting = session.query(Meeting).filter_by(id=meeting_id).first()
    if not meeting:
        session.close()
        return None

    discussions = session.query(Discussion).filter_by(meeting_id=meeting_id).all()

    from models import Attendance
    attendances = session.query(Attendance).filter_by(meeting_id=meeting_id).all()
    present_count = sum(1 for a in attendances if a.is_present)

    session.close()

    return {
        'meeting_no': meeting.meeting_no,
        'discussions': len(discussions),
        'present': present_count
    }

def calculate_improvement_metrics(original, improved, db_stats, meeting_id):
    """Calculate improvement metrics"""
    metrics = {
        'meeting_id': meeting_id,
        'meeting_no': db_stats['meeting_no'] if db_stats else 'N/A'
    }

    # Discussion count accuracy
    db_disc = db_stats['discussions'] if db_stats else 0
    orig_disc = len(original['extracted']['discussions']) if original else 0
    imp_disc = len(improved['extracted']['discussions']) if improved else 0

    # Calculate errors (absolute difference from DB)
    orig_disc_error = abs(orig_disc - db_disc)
    imp_disc_error = abs(imp_disc - db_disc)

    metrics['discussions'] = {
        'database': db_disc,
        'original_ocr': orig_disc,
        'improved_ocr': imp_disc,
        'original_error': orig_disc_error,
        'improved_error': imp_disc_error,
        'improvement': orig_disc_error - imp_disc_error,  # Positive = better
        'improvement_pct': ((orig_disc_error - imp_disc_error) / max(orig_disc_error, 1)) * 100 if orig_disc_error > 0 else 0
    }

    # Attendance accuracy
    db_present = db_stats['present'] if db_stats else 0
    orig_present = len([a for a in original['extracted']['attendances'] if original and a.get('status') == 'present']) if original else 0
    imp_present = len([a for a in improved['extracted']['attendances'] if improved and a.get('status') == 'present']) if improved else 0

    orig_present_error = abs(orig_present - db_present)
    imp_present_error = abs(imp_present - db_present)

    metrics['attendance'] = {
        'database': db_present,
        'original_ocr': orig_present,
        'improved_ocr': imp_present,
        'original_error': orig_present_error,
        'improved_error': imp_present_error,
        'improvement': orig_present_error - imp_present_error,
        'improvement_pct': ((orig_present_error - imp_present_error) / max(orig_present_error, 1)) * 100 if orig_present_error > 0 else 0
    }

    return metrics

def generate_comparison_report():
    """Generate full comparison report"""
    protocols = [101, 102, 103, 104, 105, 106]

    all_metrics = []

    print("=" * 100)
    print("OCR ALGORITHM IMPROVEMENT ANALYSIS")
    print("=" * 100)
    print()

    for meeting_id in protocols:
        original = load_ocr_results(meeting_id, 'original')
        improved = load_ocr_results(meeting_id, 'improved')
        db_stats = get_db_stats(meeting_id)

        if not db_stats:
            print(f"Protocol {meeting_id}: No database record found, skipping")
            continue

        metrics = calculate_improvement_metrics(original, improved, db_stats, meeting_id)
        all_metrics.append(metrics)

        # Print individual protocol report
        print(f"### Protocol {metrics['meeting_no']} (Meeting ID: {meeting_id})")
        print()

        # Discussions
        disc = metrics['discussions']
        print(f"**Discussions:**")
        print(f"  Database (Truth):    {disc['database']}")
        print(f"  Original OCR:        {disc['original_ocr']} (error: {disc['original_error']})")
        print(f"  Improved OCR:        {disc['improved_ocr']} (error: {disc['improved_error']})")
        if disc['improvement'] > 0:
            print(f"  Improvement:         +{disc['improvement']} ({disc['improvement_pct']:.1f}% better)")
        elif disc['improvement'] < 0:
            print(f"  Regression:          {disc['improvement']} ({disc['improvement_pct']:.1f}% worse)")
        else:
            print(f"  No change")
        print()

        # Attendance
        att = metrics['attendance']
        print(f"**Attendance:**")
        print(f"  Database (Truth):    {att['database']}")
        print(f"  Original OCR:        {att['original_ocr']} (error: {att['original_error']})")
        print(f"  Improved OCR:        {att['improved_ocr']} (error: {att['improved_error']})")
        if att['improvement'] > 0:
            print(f"  Improvement:         +{att['improvement']} ({att['improvement_pct']:.1f}% better)")
        elif att['improvement'] < 0:
            print(f"  Regression:          {att['improvement']} ({att['improvement_pct']:.1f}% worse)")
        else:
            print(f"  No change")
        print()
        print("-" * 100)
        print()

    # Overall statistics
    if all_metrics:
        total_disc_improvement = sum(m['discussions']['improvement'] for m in all_metrics)
        total_att_improvement = sum(m['attendance']['improvement'] for m in all_metrics)

        # Calculate average error reduction
        orig_disc_total_error = sum(m['discussions']['original_error'] for m in all_metrics)
        imp_disc_total_error = sum(m['discussions']['improved_error'] for m in all_metrics)

        orig_att_total_error = sum(m['attendance']['original_error'] for m in all_metrics)
        imp_att_total_error = sum(m['attendance']['improved_error'] for m in all_metrics)

        print("=" * 100)
        print("OVERALL IMPROVEMENT SUMMARY")
        print("=" * 100)
        print()
        print(f"**Protocols Analyzed:** {len(all_metrics)}")
        print()
        print(f"**Discussion Detection:**")
        print(f"  Original Total Error:  {orig_disc_total_error}")
        print(f"  Improved Total Error:  {imp_disc_total_error}")
        print(f"  Total Improvement:     {total_disc_improvement} fewer errors")
        if orig_disc_total_error > 0:
            overall_disc_pct = ((orig_disc_total_error - imp_disc_total_error) / orig_disc_total_error) * 100
            print(f"  Overall Improvement:   {overall_disc_pct:.1f}%")
        print()

        print(f"**Attendance Detection:**")
        print(f"  Original Total Error:  {orig_att_total_error}")
        print(f"  Improved Total Error:  {imp_att_total_error}")
        print(f"  Total Improvement:     {total_att_improvement} fewer errors")
        if orig_att_total_error > 0:
            overall_att_pct = ((orig_att_total_error - imp_att_total_error) / orig_att_total_error) * 100
            print(f"  Overall Improvement:   {overall_att_pct:.1f}%")
        print()
        print("=" * 100)

    # Save metrics to JSON
    with open('ocr_improvement_metrics.json', 'w', encoding='utf-8') as f:
        json.dump(all_metrics, f, ensure_ascii=False, indent=2)

    print("\n[OK] Metrics saved to: ocr_improvement_metrics.json")

if __name__ == "__main__":
    generate_comparison_report()
