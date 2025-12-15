from core.config import settings

def calculate_new_level_and_xp(current_level: int, current_xp: int, xp_gain: int):
    """
    Calculates the new level and XP based on the gain and scaling thresholds.
    
    Args:
        current_level (int): The user's current level (1-based).
        current_xp (int): The user's current XP.
        xp_gain (int): The amount of XP gained (can be positive or negative).
        
    Returns:
        tuple: (new_level, new_xp)
    """
    total_xp = current_xp + xp_gain
    new_level = current_level
    
    # Handle XP Loss (Undo logic)
    # If XP becomes negative, we might de-level.
    # For MVP simplicity: Just allow negative XP? 
    # Or strict de-leveling:
    while total_xp < 0:
        if new_level <= 1:
            # Cap at Level 1, 0 XP
            return 1, max(0, total_xp)
        
        # De-level
        new_level -= 1
        # Add the XP required for the *completed* level back to total
        # Level 2->3 req is index 1.
        # If we drop from 2 to 1, we need to know what Lvl 1->2 req was (index 0).
        threshold_index = new_level - 1
        if threshold_index < len(settings.LEVEL_XP_THRESHOLDS):
            req_xp = settings.LEVEL_XP_THRESHOLDS[threshold_index]
        else:
            req_xp = settings.LEVEL_XP_THRESHOLDS[-1]
            
        total_xp += req_xp

    # Handle XP Gain (Level Up)
    while True:
        # Determine strict threshold for current level
        # Level 1 uses index 0. Level N uses index N-1.
        threshold_index = new_level - 1
        
        if threshold_index < len(settings.LEVEL_XP_THRESHOLDS):
            required_xp = settings.LEVEL_XP_THRESHOLDS[threshold_index]
        else:
            # Fallback: Use last defined threshold or scaling?
            # User request implies "increase like this", so maybe static last value 
            # or we could make it formulaic. For now, static last value as configured.
            required_xp = settings.LEVEL_XP_THRESHOLDS[-1]
            
        if total_xp >= required_xp:
            total_xp -= required_xp
            new_level += 1
        else:
            break
            
    # Final requirement for the *new* level
    final_threshold_index = new_level - 1
    if final_threshold_index < len(settings.LEVEL_XP_THRESHOLDS):
        final_required_xp = settings.LEVEL_XP_THRESHOLDS[final_threshold_index]
    else:
        final_required_xp = settings.LEVEL_XP_THRESHOLDS[-1]
            
    return new_level, total_xp, final_required_xp
