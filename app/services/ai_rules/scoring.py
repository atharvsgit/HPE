import logging
from sqlalchemy import text
from app.db.session import metadata_engine

logger = logging.getLogger(__name__)

async def update_rule_quality_scores() -> None:
    """
    Recalculates quality scores and false positive rates for all active rules.
    This combines operational failures, AI feedback rejections, and reviewer interactions
    to update the `quality_score` and `is_noisy` flags without automatically disabling rules.
    """
    logger.info("Starting Rule Quality Scoring job...")
    
    async with metadata_engine.connect() as conn:
        async with conn.begin():
            # 1. Fetch all rules
            rules_res = await conn.execute(text("SELECT rule_id FROM dq_config.dq_rules WHERE is_enabled = true"))
            rule_ids = [row[0] for row in rules_res.fetchall()]
            
            for r_id in rule_ids:
                # 2. Get operational failure frequency (last 30 days)
                failures_res = await conn.execute(
                    text("""
                        SELECT COUNT(*) 
                        FROM dq_results.test_results 
                        WHERE rule_id = :rule_id 
                        AND status = 'FAIL' 
                        AND executed_at > NOW() - INTERVAL '30 days'
                    """),
                    {"rule_id": r_id}
                )
                failure_count = failures_res.scalar_one() or 0
                
                # 3. Get total executions
                executions_res = await conn.execute(
                    text("""
                        SELECT COUNT(*) 
                        FROM dq_results.test_results 
                        WHERE rule_id = :rule_id 
                        AND executed_at > NOW() - INTERVAL '30 days'
                    """),
                    {"rule_id": r_id}
                )
                execution_count = executions_res.scalar_one() or 1 # avoid div by zero
                
                failure_rate = failure_count / execution_count
                
                # 4. Get False Positive indicators (from llm_feedback where feedback_type = 'reject')
                # A reject on a violation batch implies the violation was a false alarm or noisy
                fp_res = await conn.execute(
                    text("""
                        SELECT COUNT(f.id) 
                        FROM dq_results.llm_feedback f
                        JOIN dq_results.violation_batches b ON f.violation_batch_id = b.id
                        WHERE b.rule_id = :rule_id 
                        AND f.feedback_type = 'reject'
                        AND f.created_at > NOW() - INTERVAL '30 days'
                    """),
                    {"rule_id": r_id}
                )
                fp_count = fp_res.scalar_one() or 0
                
                # Also count total feedbacks to get a rejection rate
                total_fb_res = await conn.execute(
                    text("""
                        SELECT COUNT(f.id) 
                        FROM dq_results.llm_feedback f
                        JOIN dq_results.violation_batches b ON f.violation_batch_id = b.id
                        WHERE b.rule_id = :rule_id 
                        AND f.created_at > NOW() - INTERVAL '30 days'
                    """),
                    {"rule_id": r_id}
                )
                total_fb_count = total_fb_res.scalar_one() or 1
                
                reviewer_rejection_rate = fp_count / total_fb_count if total_fb_count > 0 else 0.0
                
                # Approximate False Positive Rate: rejected batches / total failed batches
                # If they didn't provide feedback, we don't know if it's FP, but we'll use rejection count vs total failures
                # A more precise metric would track actual incident resolutions.
                # Here we combine signals:
                
                # Base score starts at 100
                score = 100.0
                
                # Penalize for high failure rate (alert fatigue)
                if failure_rate > 0.5:
                    score -= 10
                elif failure_rate > 0.1:
                    score -= 5
                    
                # Penalize heavily for reviewer rejections (strong signal of noise)
                score -= (reviewer_rejection_rate * 30)
                
                # Prevent negative scores
                score = max(0.0, min(100.0, score))
                
                # Determine if it's noisy
                # Is noisy if score drops below 70, or if reviewer rejection rate is very high
                is_noisy = (score < 70.0) or (reviewer_rejection_rate > 0.4)
                
                fp_rate_pct = min(100.0, (fp_count / max(1, failure_count)) * 100.0)
                
                # Update rule
                await conn.execute(
                    text("""
                        UPDATE dq_config.dq_rules
                        SET quality_score = :score,
                            is_noisy = :is_noisy,
                            false_positive_rate = :fp_rate
                        WHERE rule_id = :rule_id
                    """),
                    {
                        "score": round(score, 2),
                        "is_noisy": is_noisy,
                        "fp_rate": round(fp_rate_pct, 2),
                        "rule_id": r_id
                    }
                )
                
    logger.info("Rule Quality Scoring job completed.")
