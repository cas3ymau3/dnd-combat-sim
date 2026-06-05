
# MISCELLANEOUS 
rm(list=ls()) # clear workspace  
cat("\014") # clear console
hit_probability <- function(ac, attack_bonus, advantage = FALSE, bless = FALSE) {
  # Helper: probability of hitting with a given threshold and bless roll
  prob_hit_single <- function(threshold) {
    pmax(pmin((21 - threshold) / 20, 1), 0)
  }
  
  prob_hit_advantage <- function(threshold) {
    pmax(pmin(1 - ((threshold - 1) / 20)^2, 1), 0)
  }
  
  # Adjust threshold based on bless
  if (bless) {
    bless_vals <- 1:4
    if (advantage) {
      probs <- sapply(bless_vals, function(b) prob_hit_advantage(ac - attack_bonus - b))
    } else {
      probs <- sapply(bless_vals, function(b) prob_hit_single(ac - attack_bonus - b))
    }
    return(mean(probs))
  } else {
    threshold <- ac - attack_bonus
    if (advantage) {
      return(prob_hit_advantage(threshold))
    } else {
      return(prob_hit_single(threshold))
    }
  }
}

# TIER-01 (7.47 DPR)
{
  # LEVEL 01 - 8.29 DPR
  rm(list=ls()) # clear workspace  
  set.seed(1)
  sim_dpr <- function(n = 10000) {
    atk_bonus <- 4  # DEX + proficiency
    dmg_bonus <- 4  # DEX + dueling
    combats <- 4
    rounds_per_combat <- 4
    aoos_per_combat <- 1
    combat_rounds <- combats * rounds_per_combat  # 16 rounds
    
    roll_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:8, 2, replace = TRUE) else sample(1:8, 1)
      sum(dice) + dmg_bonus
    }
    
    roll_hit <- function(adv = FALSE) {
      rolls <- sample(1:20, if (adv) 2 else 1, replace = TRUE)
      max_roll <- max(rolls)
      list(roll = max_roll, hit = (max_roll + atk_bonus >= 13), crit = (max_roll == 20))
    }
    
    replicate(n, {
      dmg <- 0
      for (combat in 1:combats) {
        adv_next <- FALSE
        for (i in 1:(rounds_per_combat + aoos_per_combat)) {
          res <- roll_hit(adv_next)
          adv_next <- res$hit  # Vex mastery triggers advantage next round if hit
          if (res$hit) dmg <- dmg + roll_dmg(res$crit)
        }
      }
      dmg / combat_rounds  # DPR per combat round
    }) |> mean()
  }
  sim_dpr()
  
  # LEVEL 02 & LEVEL 03 - 7.39 DPR
  rm(list=ls()) # clear workspace  
  set.seed(1)
  sim_dpr <- function(n = 10000) {
    atk_bonus <- 3 + 2  # CHA modifier + proficiency
    dmg_bonus <- 3 + 2  # CHA modifier + dueling
    combats <- 4
    rounds_per_combat <- 4
    aoos_per_combat <- 1
    combat_rounds <- combats * rounds_per_combat  # 16 rounds
    
    roll_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:8, 2, replace = TRUE) else sample(1:8, 1)
      sum(dice) + dmg_bonus
    }
    
    roll_hit <- function() {
      roll <- sample(1:20, 1)
      list(roll = roll, hit = (roll + atk_bonus >= 14), crit = (roll == 20))
    }
    
    replicate(n, {
      dmg <- 0
      for (combat in 1:combats) {
        for (i in 1:(rounds_per_combat + aoos_per_combat)) {
          res <- roll_hit()
          if (res$hit) dmg <- dmg + roll_dmg(res$crit)
        }
      }
      dmg / combat_rounds  # DPR per combat round
    }) |> mean()
  }
  sim_dpr()
  
  # LEVEL 04 - 6.81
  rm(list=ls()) # clear workspace  
  set.seed(1)
  sim_dpr <- function(n = 10000) {
    atk_bonus <- 3 + 2  # CHA modifier + proficiency
    dmg_bonus <- 3 + 2  # CHA modifier + dueling
    combats <- 4
    rounds_per_combat <- 4
    aoos_per_combat <- 1
    combat_rounds <- combats * rounds_per_combat  # 16 rounds
    
    roll_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:8, 2, replace = TRUE) else sample(1:8, 1)
      sum(dice) + dmg_bonus
    }
    
    roll_hit <- function() {
      roll <- sample(1:20, 1)
      list(roll = roll, hit = (roll + atk_bonus >= 15), crit = (roll == 20))
    }
    
    replicate(n, {
      dmg <- 0
      for (combat in 1:combats) {
        for (i in 1:(rounds_per_combat + aoos_per_combat)) {
          res <- roll_hit()
          if (res$hit) dmg <- dmg + roll_dmg(res$crit)
        }
      }
      dmg / combat_rounds  # DPR per combat round
    }) |> mean()
  }
  sim_dpr()

  # tier-01 avg: 7.47 DPR 
}
  
# TIER 02
{
  
  # LEVEL 05 - 16.71 DPR
  {
    rm(list=ls()) # clear workspace
    set.seed(42)
    
    # Parameters
    rounds_per_combat <- 4
    combats <- 4
    combat_rounds <- rounds_per_combat * combats
    aoo_total <- combats
    ac <- 15
    
    # Character parameters
    cha_mod <- 3
    prof_bonus <- 3
    dueling_bonus <- 2
    magic_bonus <- 1
    
    weapon_die <- 8
    true_strike_die <- 6
    
    # --- Attack roll ---
    # Pass magic_active = TRUE/FALSE each time
    attack_roll <- function(magic_active = FALSE) {
      roll <- sample(1:20, 1)
      atk_bonus <- cha_mod + prof_bonus + ifelse(magic_active, magic_bonus, 0)
      list(roll = roll, total = roll + atk_bonus, crit = roll == 20)
    }
    
    # --- Weapon damage ---
    weapon_dmg <- function(crit = FALSE, magic_active = FALSE) {
      dice <- if (crit) sample(1:weapon_die, 2, replace = TRUE) else sample(1:weapon_die, 1)
      dmg_bonus <- cha_mod + dueling_bonus + ifelse(magic_active, magic_bonus, 0)
      sum(dice) + dmg_bonus
    }
    
    # --- True Strike damage ---
    true_strike_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:true_strike_die, 2, replace = TRUE) else sample(1:true_strike_die, 1)
      sum(dice)
    }
    
    # Simulate one adventuring day
    simulate_day <- function() {
      total_dmg <- 0
      guided_left <- 2   # start with 2 uses
      guided_used_total <- 0
      war_priest_charges <- 3
      war_priest_used_total <- 0
      aoo_left <- aoo_total
      
      total_attacks <- 0
      total_hits <- 0
      total_crits <- 0
      
      for (combat in 1:combats) {
        # Determine if Magic Weapon is active for this combat
        magic_active <- runif(1) < 0.33
        
        for (round in 1:rounds_per_combat) {
          guided_used_this_turn <- FALSE
          
          # --- Main attack ---
          atk <- attack_roll(magic_active = magic_active)
          total_attacks <- total_attacks + 1
          hit <- atk$total >= ac || atk$crit
          if (!hit && !guided_used_this_turn && guided_left > 0 && atk$total + 10 >= ac) {
            hit <- TRUE
            guided_used_this_turn <- TRUE
            guided_left <- guided_left - 1
            guided_used_total <- guided_used_total + 1
          }
          
          if (hit) {
            total_hits <- total_hits + 1
            if (atk$crit) total_crits <- total_crits + 1
            # Damage = weapon + true strike, both already include correct bonuses
            dmg <- weapon_dmg(atk$crit, magic_active) + true_strike_dmg(atk$crit)
            total_dmg <- total_dmg + dmg
          }
          
          # --- War Priest bonus attack ---
          if (war_priest_charges > 0) {
            war_priest_charges <- war_priest_charges - 1
            war_priest_used_total <- war_priest_used_total + 1
            atk2 <- attack_roll(magic_active = magic_active)
            total_attacks <- total_attacks + 1
            hit2 <- atk2$total >= ac || atk2$crit
            if (!hit2 && !guided_used_this_turn && guided_left > 0 && atk2$total + 10 >= ac) {
              hit2 <- TRUE
              guided_used_this_turn <- TRUE
              guided_left <- guided_left - 1
              guided_used_total <- guided_used_total + 1
            }
            if (hit2) {
              total_hits <- total_hits + 1
              if (atk2$crit) total_crits <- total_crits + 1
              dmg2 <- weapon_dmg(atk2$crit, magic_active)
              total_dmg <- total_dmg + dmg2
            }
          }
        }
        
        # --- Attack of opportunity ---
        if (aoo_left > 0) {
          aoo_left <- aoo_left - 1
          atk3 <- attack_roll(magic_active = magic_active)
          total_attacks <- total_attacks + 1
          hit3 <- atk3$total >= ac || atk3$crit
          if (!hit3 && guided_left > 0 && atk3$total + 10 >= ac) {
            hit3 <- TRUE
            guided_left <- guided_left - 1
            guided_used_total <- guided_used_total + 1
          }
          if (hit3) {
            total_hits <- total_hits + 1
            if (atk3$crit) total_crits <- total_crits + 1
            dmg3 <- weapon_dmg(atk3$crit, magic_active)
            total_dmg <- total_dmg + dmg3
          }
        }
        
        # --- Resource recovery after certain combats ---
        if (combat == 1) { # after combat 1, Prayer of Healing
          guided_left <- min(2, guided_left + 1)
          war_priest_charges <- 3
        }
        if (combat == 3) { # after combat 3, Short Rest
          guided_left <- min(2, guided_left + 1)
          war_priest_charges <- 3
        }
      }
      
      list(
        dpr = total_dmg / combat_rounds,
        attacks = total_attacks,
        hits = total_hits,
        crits = total_crits,
        guided_used = guided_used_total,
        war_priest_used = war_priest_used_total
      )
    } 
    
    # Run simulation
    sims <- replicate(10000, simulate_day(), simplify = FALSE)
    dprs <- sapply(sims, function(x) x$dpr)
    attacks <- sum(sapply(sims, function(x) x$attacks))
    hits <- sum(sapply(sims, function(x) x$hits))
    crits <- sum(sapply(sims, function(x) x$crits))
    guided_uses <- mean(sapply(sims, function(x) x$guided_used))
    war_priest_uses <- mean(sapply(sims, function(x) x$war_priest_used))
    
    # Summary
    cat("Average DPR:", mean(dprs), "\n")
    cat("Hit rate:", hits / attacks, "\n")
    cat("Crit rate:", crits / attacks, "\n")
    cat("Miss rate:", 1 - hits / attacks, "\n")
    cat("Average Guided Strikes used per day:", guided_uses, "\n")
    cat("Average War Priest bonus attacks used per day:", war_priest_uses, "\n")
  }
  
  # LEVEL 06 - 20.90 DPR 
  {
    rm(list=ls())
    set.seed(42)
    
    # Parameters
    rounds_per_combat <- 4
    combats <- 4
    combat_rounds <- rounds_per_combat * combats
    aoo_total <- combats
    ac <- 15
    cha_mod <- 4   # CHA 18
    prof_bonus <- 3
    dueling_bonus <- 2
    magic_bonus <- 1
    weapon_die <- 8
    true_strike_die <- 6
    wrathful_die <- 6
    
    # Damage functions
    weapon_dmg <- function(crit = FALSE, magic_active = FALSE) {
      dice <- if (crit) sample(1:weapon_die, 2, replace = TRUE) else sample(1:weapon_die, 1)
      dmg_bonus <- cha_mod + dueling_bonus + ifelse(magic_active, magic_bonus, 0)
      sum(dice) + dmg_bonus
    }
    true_strike_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:true_strike_die, 2, replace = TRUE) else sample(1:true_strike_die, 1)
      sum(dice)
    }
    wrathful_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:wrathful_die, 2, replace = TRUE) else sample(1:wrathful_die, 1)
      sum(dice)
    }
    
    # Attack roll
    attack_roll <- function(magic_active = FALSE) {
      roll <- sample(1:20, 1)
      atk_bonus <- cha_mod + prof_bonus + ifelse(magic_active, magic_bonus, 0)
      list(roll = roll, total = roll + atk_bonus, crit = roll == 20)
    }
    
    # Simulate one adventuring day
    simulate_day <- function() {
      total_dmg <- 0
      guided_left <- 2
      guided_used_total <- 0
      war_priest_charges <- 3
      war_priest_used_total <- 0
      aoo_left <- aoo_total
      
      # Wrathful smite resources
      wrathful_free <- 1
      cleric_slots <- 4
      pact_slots <- 1
      wrathful_used_total <- 0
      
      total_attacks <- 0
      total_hits <- 0
      total_crits <- 0
      
      # Randomly choose 2 combats for Magic Weapon
      magic_combats <- sample(1:combats, 2)
      
      for (combat in 1:combats) {
        magic_active <- combat %in% magic_combats
        
        for (round in 1:rounds_per_combat) {
          guided_used_this_turn <- FALSE
          wrathful_cast_this_turn <- FALSE
          
          # --- Main attack ---
          atk <- attack_roll(magic_active = magic_active)
          total_attacks <- total_attacks + 1
          hit <- atk$total >= ac || atk$crit
          used_guided <- FALSE
          if (!hit && !guided_used_this_turn && guided_left > 0 && atk$total + 10 >= ac) {
            hit <- TRUE
            guided_used_this_turn <- TRUE
            guided_left <- guided_left - 1
            guided_used_total <- guided_used_total + 1
            used_guided <- TRUE
          }
          
          if (hit) {
            total_hits <- total_hits + 1
            if (atk$crit) total_crits <- total_crits + 1
            dmg <- weapon_dmg(atk$crit, magic_active) + true_strike_dmg(atk$crit)
            
            # Wrathful smite trigger conditions
            if ((war_priest_charges == 0 || used_guided || atk$crit) &&
                (wrathful_free > 0 || cleric_slots > 0 || pact_slots > 0)) {
              wrathful_cast_this_turn <- TRUE
              wrathful_used_total <- wrathful_used_total + 1
              if (wrathful_free > 0) {
                wrathful_free <- wrathful_free - 1
              } else if (pact_slots > 0) {
                pact_slots <- pact_slots - 1
              } else if (cleric_slots > 0) {
                cleric_slots <- cleric_slots - 1
              }
              dmg <- dmg + wrathful_dmg(atk$crit)
            }
            
            total_dmg <- total_dmg + dmg
          }
          
          # --- War Priest bonus attack ---
          if (war_priest_charges > 0 && !wrathful_cast_this_turn) {
            war_priest_charges <- war_priest_charges - 1
            war_priest_used_total <- war_priest_used_total + 1
            atk2 <- attack_roll(magic_active = magic_active)
            total_attacks <- total_attacks + 1
            hit2 <- atk2$total >= ac || atk2$crit
            if (!hit2 && !guided_used_this_turn && guided_left > 0 && atk2$total + 10 >= ac) {
              hit2 <- TRUE
              guided_used_this_turn <- TRUE
              guided_left <- guided_left - 1
              guided_used_total <- guided_used_total + 1
            }
            if (hit2) {
              total_hits <- total_hits + 1
              if (atk2$crit) total_crits <- total_crits + 1
              dmg2 <- weapon_dmg(atk2$crit, magic_active)
              total_dmg <- total_dmg + dmg2
            }
          }
        }
        
        # --- Attack of opportunity ---
        if (aoo_left > 0) {
          aoo_left <- aoo_left - 1
          atk3 <- attack_roll(magic_active = magic_active)
          total_attacks <- total_attacks + 1
          hit3 <- atk3$total >= ac || atk3$crit
          if (!hit3 && guided_left > 0 && atk3$total + 10 >= ac) {
            hit3 <- TRUE
            guided_left <- guided_left - 1
            guided_used_total <- guided_used_total + 1
          }
          if (hit3) {
            total_hits <- total_hits + 1
            if (atk3$crit) total_crits <- total_crits + 1
            dmg3 <- weapon_dmg(atk3$crit, magic_active)
            total_dmg <- total_dmg + dmg3
          }
        }
        
        # --- Resource recovery ---
        if (combat == 1) { # after combat 1, Prayer of Healing
          guided_left <- min(2, guided_left + 1)
          war_priest_charges <- 3
          pact_slots <- 1
        }
        if (combat == 3) { # after combat 3, Short Rest
          guided_left <- min(2, guided_left + 1)
          war_priest_charges <- 3
          pact_slots <- 1
        }
      }
      
      list(
        dpr = total_dmg / combat_rounds,
        attacks = total_attacks,
        hits = total_hits,
        crits = total_crits,
        guided_used = guided_used_total,
        war_priest_used = war_priest_used_total,
        wrathful_used = wrathful_used_total
      )
    }
    
    # Run simulation
    sims <- replicate(10000, simulate_day(), simplify = FALSE)
    dprs <- sapply(sims, function(x) x$dpr)
    attacks <- sum(sapply(sims, function(x) x$attacks))
    hits <- sum(sapply(sims, function(x) x$hits))
    crits <- sum(sapply(sims, function(x) x$crits))
    guided_uses <- mean(sapply(sims, function(x) x$guided_used))
    war_priest_uses <- mean(sapply(sims, function(x) x$war_priest_used))
    wrathful_uses <- mean(sapply(sims, function(x) x$wrathful_used))
    
    # Summary
    cat("Average DPR:", mean(dprs), "\n")
    cat("Hit rate:", hits / attacks, "\n")
    cat("Crit rate:", crits / attacks, "\n")
    cat("Miss rate:", 1 - hits / attacks, "\n")
    cat("Average Guided Strikes used per day:", guided_uses, "\n")
    cat("Average War Priest bonus attacks used per day:", war_priest_uses, "\n")
    cat("Average Wrathful Smites used per day:", wrathful_uses, "\n")
  }
  
  # LEVEL 07 - 21.03 DPR 
  {
    rm(list=ls())
    set.seed(42)
    
    # Parameters
    rounds_per_combat <- 4
    combats <- 4
    combat_rounds <- rounds_per_combat * combats
    aoo_total <- combats
    ac <- 16
    
    # Character parameters (level 7)
    cha_mod <- 4   # CHA 18
    prof_bonus <- 3
    dueling_bonus <- 2
    magic_bonus <- 1
    weapon_die <- 8
    true_strike_die <- 6
    wrathful_die <- 6
    
    # --- Damage functions ---
    weapon_dmg <- function(crit = FALSE, magic_active = FALSE) {
      dice <- if (crit) sample(1:weapon_die, 2, replace = TRUE) else sample(1:weapon_die, 1)
      dmg_bonus <- cha_mod + dueling_bonus + ifelse(magic_active, magic_bonus, 0)
      sum(dice) + dmg_bonus
    }
    true_strike_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:true_strike_die, 2, replace = TRUE) else sample(1:true_strike_die, 1)
      sum(dice)
    }
    wrathful_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:wrathful_die, 2, replace = TRUE) else sample(1:wrathful_die, 1)
      sum(dice)
    }
    
    # --- Attack roll ---
    attack_roll <- function(magic_active = FALSE) {
      roll <- sample(1:20, 1)
      atk_bonus <- cha_mod + prof_bonus + ifelse(magic_active, magic_bonus, 0)
      list(roll = roll, total = roll + atk_bonus, crit = roll == 20)
    }
    
    # Simulate one adventuring day
    simulate_day <- function() {
      total_dmg <- 0
      guided_left <- 2
      guided_used_total <- 0
      war_priest_charges <- 3
      war_priest_used_total <- 0
      aoo_left <- aoo_total
      
      # Wrathful smite resources
      wrathful_free <- 1
      cleric_slots <- 4
      pact_slots <- 1
      wrathful_used_total <- 0
      
      # Action Surge resources
      action_surge_left <- 1
      action_surge_used_total <- 0
      action_surge_with_magic <- 0
      action_surge_23_used <- FALSE  # ensure exactly one use across combats 2 & 3
      
      total_attacks <- 0
      total_hits <- 0
      total_crits <- 0
      
      # Randomly choose 2 combats for Magic Weapon
      magic_combats <- sample(1:combats, 2)
      
      for (combat in 1:combats) {
        magic_active <- combat %in% magic_combats
        
        # Decide if Action Surge should be used in this combat
        use_action_surge_this_combat <- FALSE
        if (combat == 1) {
          use_action_surge_this_combat <- TRUE
        } else if (combat == 2) {
          use_action_surge_this_combat <- magic_active && !action_surge_23_used
        } else if (combat == 3) {
          use_action_surge_this_combat <- !action_surge_23_used
        } else if (combat == 4) {
          use_action_surge_this_combat <- TRUE
        }
        
        action_surge_used_in_this_combat <- FALSE
        
        for (round in 1:rounds_per_combat) {
          guided_used_this_turn <- FALSE
          wrathful_cast_this_turn <- FALSE
          
          # --- Main attack ---
          atk <- attack_roll(magic_active = magic_active)
          total_attacks <- total_attacks + 1
          hit <- atk$total >= ac || atk$crit
          used_guided <- FALSE
          if (!hit && !guided_used_this_turn && guided_left > 0 && atk$total + 10 >= ac) {
            hit <- TRUE
            guided_used_this_turn <- TRUE
            guided_left <- guided_left - 1
            guided_used_total <- guided_used_total + 1
            used_guided <- TRUE
          }
          
          if (hit) {
            total_hits <- total_hits + 1
            if (atk$crit) total_crits <- total_crits + 1
            dmg <- weapon_dmg(atk$crit, magic_active) + true_strike_dmg(atk$crit)
            
            # Wrathful smite trigger conditions
            if ((war_priest_charges == 0 || used_guided || atk$crit) &&
                (wrathful_free > 0 || cleric_slots > 0 || pact_slots > 0)) {
              wrathful_cast_this_turn <- TRUE
              wrathful_used_total <- wrathful_used_total + 1
              if (wrathful_free > 0) {
                wrathful_free <- wrathful_free - 1
              } else if (pact_slots > 0) {
                pact_slots <- pact_slots - 1
              } else if (cleric_slots > 0) {
                cleric_slots <- cleric_slots - 1
              }
              dmg <- dmg + wrathful_dmg(atk$crit)
            }
            
            total_dmg <- total_dmg + dmg
          }
          
          # --- War Priest bonus attack ---
          if (war_priest_charges > 0 && !wrathful_cast_this_turn) {
            war_priest_charges <- war_priest_charges - 1
            war_priest_used_total <- war_priest_used_total + 1
            atk2 <- attack_roll(magic_active = magic_active)
            total_attacks <- total_attacks + 1
            hit2 <- atk2$total >= ac || atk2$crit
            if (!hit2 && !guided_used_this_turn && guided_left > 0 && atk2$total + 10 >= ac) {
              hit2 <- TRUE
              guided_used_this_turn <- TRUE
              guided_left <- guided_left - 1
              guided_used_total <- guided_used_total + 1
            }
            if (hit2) {
              total_hits <- total_hits + 1
              if (atk2$crit) total_crits <- total_crits + 1
              dmg2 <- weapon_dmg(atk2$crit, magic_active)
              total_dmg <- total_dmg + dmg2
            }
          }
          
          # --- Action Surge attack (once per chosen combat) ---
          if (use_action_surge_this_combat && !action_surge_used_in_this_combat && action_surge_left > 0) {
            action_surge_left <- action_surge_left - 1
            action_surge_used_in_this_combat <- TRUE
            action_surge_used_total <- action_surge_used_total + 1
            if (combat == 2 || combat == 3) action_surge_23_used <- TRUE
            
            atk_as <- attack_roll(magic_active = magic_active)
            total_attacks <- total_attacks + 1
            hit_as <- atk_as$total >= ac || atk_as$crit
            if (!hit_as && !guided_used_this_turn && guided_left > 0 && atk_as$total + 10 >= ac) {
              hit_as <- TRUE
              guided_used_this_turn <- TRUE
              guided_left <- guided_left - 1
              guided_used_total <- guided_used_total + 1
            }
            if (hit_as) {
              total_hits <- total_hits + 1
              if (atk_as$crit) total_crits <- total_crits + 1
              # Action Surge attack: weapon only
              dmg_as <- weapon_dmg(atk_as$crit, magic_active)
              total_dmg <- total_dmg + dmg_as
            }
            if (magic_active) action_surge_with_magic <- action_surge_with_magic + 1
          }
        }
        
        # --- Attack of opportunity ---
        if (aoo_left > 0) {
          aoo_left <- aoo_left - 1
          atk3 <- attack_roll(magic_active = magic_active)
          total_attacks <- total_attacks + 1
          hit3 <- atk3$total >= ac || atk3$crit
          if (!hit3 && guided_left > 0 && atk3$total + 10 >= ac) {
            hit3 <- TRUE
            guided_left <- guided_left - 1
            guided_used_total <- guided_used_total + 1
          }
          if (hit3) {
            total_hits <- total_hits + 1
            if (atk3$crit) total_crits <- total_crits + 1
            dmg3 <- weapon_dmg(atk3$crit, magic_active)
            total_dmg <- total_dmg + dmg3
          }
        }
        
        # --- Resource recovery ---
        if (combat == 1) { # after combat 1, Prayer of Healing
          guided_left <- min(2, guided_left + 1)
          war_priest_charges <- 3
          pact_slots <- 1
          action_surge_left <- min(1, action_surge_left + 1)
        }
        if (combat == 3) { # after combat 3, Short Rest
          guided_left <- min(2, guided_left + 1)
          war_priest_charges <- 3
          pact_slots <- 1
          action_surge_left <- min(1, action_surge_left + 1)
        }
      } # end combat loop
      
      list(
        dpr = total_dmg / combat_rounds,
        attacks = total_attacks,
        hits = total_hits,
        crits = total_crits,
        guided_used = guided_used_total,
        war_priest_used = war_priest_used_total,
        wrathful_used = wrathful_used_total,
        action_surge_used = action_surge_used_total,
        action_surge_with_magic = action_surge_with_magic
      )
    }
    
    # Run simulation
    sims <- replicate(10000, simulate_day(), simplify = FALSE)
    dprs <- sapply(sims, function(x) x$dpr)
    attacks <- sum(sapply(sims, function(x) x$attacks))
    hits <- sum(sapply(sims, function(x) x$hits))
    crits <- sum(sapply(sims, function(x) x$crits))
    guided_uses <- mean(sapply(sims, function(x) x$guided_used))
    war_priest_uses <- mean(sapply(sims, function(x) x$war_priest_used))
    wrathful_uses <- mean(sapply(sims, function(x) x$wrathful_used))
    action_surge_uses <- mean(sapply(sims, function(x) x$action_surge_used))
    action_surge_with_magic_avg <- mean(sapply(sims, function(x) x$action_surge_with_magic))
    
    # Summary
    cat("Average DPR:", mean(dprs), "\n")
    cat("Hit rate:", hits / attacks, "\n")
    cat("Crit rate:", crits / attacks, "\n")
    cat("Miss rate:", 1 - hits / attacks, "\n")
    cat("Average Guided Strikes used per day:", guided_uses, "\n")
    cat("Average War Priest bonus attacks used per day:", war_priest_uses, "\n")
    cat("Average Wrathful Smites used per day:", wrathful_uses, "\n")
    cat("Average Action Surges used per day:", action_surge_uses, "\n")
    cat("Avg. share of Action Surges with Magic Weapon:", action_surge_with_magic_avg / action_surge_uses, "\n")
  }
  
  # LEVEL 08 - 23.30 DPR 
  {
    rm(list=ls())
    set.seed(42)
    
    # Parameters
    rounds_per_combat <- 4
    combats <- 4
    combat_rounds <- rounds_per_combat * combats
    ac <- 16
    
    # Character parameters (level 8)
    cha_mod <- 4   # CHA 18
    prof_bonus <- 3
    dueling_bonus <- 2
    magic_bonus <- 1
    weapon_die <- 8
    true_strike_die <- 6
    wrathful_die <- 6
    
    # --- Damage functions ---
    weapon_dmg <- function(crit = FALSE, magic_active = FALSE) {
      dice <- if (crit) sample(1:weapon_die, 2, replace=TRUE) else sample(1:weapon_die, 1)
      dmg_bonus <- cha_mod + dueling_bonus + ifelse(magic_active, magic_bonus, 0)
      sum(dice) + dmg_bonus
    }
    true_strike_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:true_strike_die, 2, replace=TRUE) else sample(1:true_strike_die, 1)
      sum(dice)
    }
    wrathful_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:wrathful_die, 2, replace=TRUE) else sample(1:wrathful_die, 1)
      sum(dice)
    }
    
    # --- Attack roll with optional advantage ---
    attack_roll <- function(magic_active = FALSE, adv = FALSE) {
      if (adv) {
        rolls <- sample(1:20, 2, replace=TRUE)
        roll <- max(rolls)
      } else {
        roll <- sample(1:20, 1)
      }
      atk_bonus <- cha_mod + prof_bonus + ifelse(magic_active, magic_bonus, 0)
      list(roll = roll, total = roll + atk_bonus, crit = (roll == 20))
    }
    
    # Simulate one adventuring day
    simulate_day <- function() {
      # Resource pools (day-level)
      guided_left <- 2
      war_priest_charges <- 3
      wrathful_free <- 1
      cleric_slots <- 4
      pact_slots <- 1
      action_surge_left <- 1
      brutality_charges <- 4
      
      # Tracking (day-level)
      total_dmg <- 0
      total_attacks <- 0
      total_hits <- 0
      total_crits <- 0
      total_advantage_attacks <- 0
      
      guided_used_total <- 0
      war_priest_used_total <- 0
      wrathful_used_total <- 0
      action_surge_used_total <- 0
      action_surge_with_magic <- 0
      brutality_used_total <- 0
      
      # Per-combat tracking
      combat_stats <- list()
      
      # Randomly choose 2 combats for Magic Weapon
      magic_combats <- sample(1:combats, 2)
      
      for (combat in 1:combats) {
        magic_active <- combat %in% magic_combats
        vexed <- FALSE
        aoo_round <- sample(1:rounds_per_combat, 1)
        
        # Local counters
        dmg_c <- 0; att_c <- 0; hit_c <- 0; crit_c <- 0
        gs_c <- 0; wp_c <- 0; ws_c <- 0; as_c <- 0; br_c <- 0
        adv_c <- 0
        
        # Guided Strike limiter only for combat 1
        guided_used_in_combat <- FALSE
        
        # Determine mode
        mode <- "setup"
        if (combat %in% c(2, 3)) {
          if (magic_active || (combat == 3 && war_priest_charges > 0)) {
            mode <- "setup"
          } else {
            mode <- "ts_only"
          }
        }
        if (combat == 4) mode <- "setup_any_gs"
        
        for (round in 1:rounds_per_combat) {
         
          # --- Action Surge on round 1 in setup modes ---
          if (round == 1 && mode != "ts_only") {
            if (action_surge_left > 0) {
              action_surge_left <- action_surge_left - 1
              action_surge_used_total <- action_surge_used_total + 1; as_c <- as_c + 1
              
              atk_as <- attack_roll(magic_active, adv = vexed)
              if (vexed) { adv_c <- adv_c + 1; total_advantage_attacks <- total_advantage_attacks + 1 }
              vexed <- FALSE
              att_c <- att_c + 1; total_attacks <- total_attacks + 1
              
              hit_as <- (atk_as$total >= ac) || atk_as$crit
              
              if (!hit_as && guided_left > 0) {
                if (combat == 1 && !guided_used_in_combat) {
                  # combat 1: only once per combat
                  hit_as <- TRUE
                  guided_left <- guided_left - 1
                  guided_used_total <- guided_used_total + 1
                  gs_c <- gs_c + 1
                  guided_used_in_combat <- TRUE
                } else if (combat != 1) {
                  # combats 2–4: no per-combat limit
                  hit_as <- TRUE
                  guided_left <- guided_left - 1
                  guided_used_total <- guided_used_total + 1
                  gs_c <- gs_c + 1
                }
              }
              
              if (hit_as) {
                hit_c <- hit_c + 1; total_hits <- total_hits + 1
                if (atk_as$crit) { crit_c <- crit_c + 1; total_crits <- total_crits + 1 }
                dmg_as <- weapon_dmg(atk_as$crit, magic_active)
                dmg_c <- dmg_c + dmg_as; total_dmg <- total_dmg + dmg_as
                if (brutality_charges > 0 && mode != "ts_only") {
                  brutality_charges <- brutality_charges - 1
                  brutality_used_total <- brutality_used_total + 1
                  br_c <- br_c + 1
                  vexed <- TRUE
                }
              }
              if (magic_active) action_surge_with_magic <- action_surge_with_magic + 1
            }
          }
          
          # --- War Priest on rounds 2-4 in setup modes ---
          if (mode != "ts_only" && round >= 2) {
            if (war_priest_charges > 0) {
              war_priest_charges <- war_priest_charges - 1
              war_priest_used_total <- war_priest_used_total + 1; wp_c <- wp_c + 1
              
              atk_wp <- attack_roll(magic_active, adv = vexed)
              if (vexed) { adv_c <- adv_c + 1; total_advantage_attacks <- total_advantage_attacks + 1 }
              vexed <- FALSE
              att_c <- att_c + 1; total_attacks <- total_attacks + 1
              
              hit_wp <- (atk_wp$total >= ac) || atk_wp$crit
              
              if (!hit_wp && guided_left > 0) {
                if (combat == 1 && !guided_used_in_combat) {
                  hit_wp <- TRUE
                  guided_left <- guided_left - 1
                  guided_used_total <- guided_used_total + 1
                  gs_c <- gs_c + 1
                  guided_used_in_combat <- TRUE
                } else if (combat != 1) {
                  hit_wp <- TRUE
                  guided_left <- guided_left - 1
                  guided_used_total <- guided_used_total + 1
                  gs_c <- gs_c + 1
                }
              }
              
              if (hit_wp) {
                hit_c <- hit_c + 1; total_hits <- total_hits + 1
                if (atk_wp$crit) { crit_c <- crit_c + 1; total_crits <- total_crits + 1 }
                dmg_wp <- weapon_dmg(atk_wp$crit, magic_active)
                dmg_c <- dmg_c + dmg_wp; total_dmg <- total_dmg + dmg_wp
                if (brutality_charges > 0 && mode != "ts_only") {
                  brutality_charges <- brutality_charges - 1
                  brutality_used_total <- brutality_used_total + 1
                  br_c <- br_c + 1
                  vexed <- TRUE
                }
              }
            }
          }
          
          # --- True Strike attack every round ---
          atk_ts <- attack_roll(magic_active, adv = vexed)
          if (vexed) { adv_c <- adv_c + 1; total_advantage_attacks <- total_advantage_attacks + 1 }
          vexed <- FALSE
          att_c <- att_c + 1; total_attacks <- total_attacks + 1
          
          hit_ts <- (atk_ts$total >= ac) || atk_ts$crit
          
          if (!hit_ts && guided_left > 0) {
            if (combat == 1 && !guided_used_in_combat && round >= 3) {
              hit_ts <- TRUE
              guided_left <- guided_left - 1
              guided_used_total <- guided_used_total + 1
              gs_c <- gs_c + 1
              guided_used_in_combat <- TRUE
            } else if (combat != 1) {
              hit_ts <- TRUE
              guided_left <- guided_left - 1
              guided_used_total <- guided_used_total + 1
              gs_c <- gs_c + 1
            }
          }
          
          # Wrathful smite logic
          add_wrathful <- FALSE
          if (mode == "ts_only") {
            if (wrathful_free > 0) { wrathful_free <- wrathful_free - 1; add_wrathful <- TRUE }
            else if (pact_slots > 0) { pact_slots <- pact_slots - 1; add_wrathful <- TRUE }
            else if (cleric_slots > 0) { cleric_slots <- cleric_slots - 1; add_wrathful <- TRUE }
          } else {
            if (round == 1) {
              if (pact_slots > 0) { pact_slots <- pact_slots - 1; add_wrathful <- TRUE }
              else if (cleric_slots > 0) { cleric_slots <- cleric_slots - 1; add_wrathful <- TRUE }
            }
          }
          if (add_wrathful) { wrathful_used_total <- wrathful_used_total + 1; ws_c <- ws_c + 1 }
          
          if (hit_ts) {
            hit_c <- hit_c + 1; total_hits <- total_hits + 1
            if (atk_ts$crit) { crit_c <- crit_c + 1; total_crits <- total_crits + 1 }
            dmg_ts <- weapon_dmg(atk_ts$crit, magic_active) + true_strike_dmg(atk_ts$crit)
            if (add_wrathful) dmg_ts <- dmg_ts + wrathful_dmg(atk_ts$crit)
            dmg_c <- dmg_c + dmg_ts; total_dmg <- total_dmg + dmg_ts
          }
          
          # --- AoO if this is the chosen round ---
          if (round == aoo_round) {
            atk_aoo <- attack_roll(magic_active, adv = vexed)
            if (vexed) { adv_c <- adv_c + 1; total_advantage_attacks <- total_advantage_attacks + 1 }
            vexed <- FALSE
            att_c <- att_c + 1; total_attacks <- total_attacks + 1
            
            hit_aoo <- (atk_aoo$total >= ac) || atk_aoo$crit
            
            if (!hit_aoo && guided_left > 0) {
              if (combat == 1 && !guided_used_in_combat && round >= 3) {
                hit_aoo <- TRUE
                guided_left <- guided_left - 1
                guided_used_total <- guided_used_total + 1
                gs_c <- gs_c + 1
                guided_used_in_combat <- TRUE
              } else if (combat != 1) {
                hit_aoo <- TRUE
                guided_left <- guided_left - 1
                guided_used_total <- guided_used_total + 1
                gs_c <- gs_c + 1
              }
            }
            
            if (hit_aoo) {
              hit_c <- hit_c + 1; total_hits <- total_hits + 1
              if (atk_aoo$crit) { crit_c <- crit_c + 1; total_crits <- total_crits + 1 }
              dmg_aoo <- weapon_dmg(atk_aoo$crit, magic_active)
              dmg_c <- dmg_c + dmg_aoo; total_dmg <- total_dmg + dmg_aoo
              if (brutality_charges > 0 && mode != "ts_only") {
                brutality_charges <- brutality_charges - 1
                brutality_used_total <- brutality_used_total + 1
                br_c <- br_c + 1
                vexed <- TRUE
              }
            }
          }
        } # end round loop
        
        # Resource recovery after combats 1 and 3
        if (combat == 1 || combat == 3) {
          guided_left <- min(2, guided_left + 1)
          war_priest_charges <- 3
          pact_slots <- 1
          action_surge_left <- 1
          brutality_charges <- 4
        }
        
        # Save per‑combat stats
        combat_stats[[combat]] <- list(
          dmg = dmg_c, att = att_c, hits = hit_c, crits = crit_c,
          gs = gs_c, wp = wp_c, ws = ws_c, `as` = as_c, br = br_c, adv = adv_c
        )
      } # end combat loop
      
      list(
        total_dpr = total_dmg / combat_rounds,
        total_attacks = total_attacks,
        total_hits = total_hits,
        total_crits = total_crits,
        guided_used = guided_used_total,
        war_priest_used = war_priest_used_total,
        wrathful_used = wrathful_used_total,
        action_surge_used = action_surge_used_total,
        action_surge_with_magic = action_surge_with_magic,
        brutality_used = brutality_used_total,
        advantage_attacks = total_advantage_attacks,
        combat_stats = combat_stats
      )
    }
    
    # Run simulation
    sims <- replicate(1000, simulate_day(), simplify=FALSE)
    
    # Aggregate totals
    dprs <- sapply(sims, function(x) x$total_dpr)
    attacks <- sum(sapply(sims, function(x) x$total_attacks))
    hits <- sum(sapply(sims, function(x) x$total_hits))
    crits <- sum(sapply(sims, function(x) x$total_crits))
    guided_uses <- mean(sapply(sims, function(x) x$guided_used))
    war_priest_uses <- mean(sapply(sims, function(x) x$war_priest_used))
    wrathful_uses <- mean(sapply(sims, function(x) x$wrathful_used))
    action_surge_uses <- mean(sapply(sims, function(x) x$action_surge_used))
    action_surge_with_magic_avg <- mean(sapply(sims, function(x) x$action_surge_with_magic))
    brutality_uses <- mean(sapply(sims, function(x) x$brutality_used))
    advantage_attacks <- sum(sapply(sims, function(x) x$advantage_attacks))
    
    # ---- Per-combat averages ----
    combat_means <- lapply(1:4, function(c) {
      dmg <- mean(sapply(sims, function(x) x$combat_stats[[c]]$dmg))
      att <- mean(sapply(sims, function(x) x$combat_stats[[c]]$att))
      hits <- mean(sapply(sims, function(x) x$combat_stats[[c]]$hits))
      crits <- mean(sapply(sims, function(x) x$combat_stats[[c]]$crits))
      gs <- mean(sapply(sims, function(x) x$combat_stats[[c]]$gs))
      wp <- mean(sapply(sims, function(x) x$combat_stats[[c]]$wp))
      ws <- mean(sapply(sims, function(x) x$combat_stats[[c]]$ws))
      asu <- mean(sapply(sims, function(x) x$combat_stats[[c]]$`as`))
      br <- mean(sapply(sims, function(x) x$combat_stats[[c]]$br))
      adv <- mean(sapply(sims, function(x) x$combat_stats[[c]]$adv))
      list(dmg=dmg, att=att, hits=hits, crits=crits,
           gs=gs, wp=wp, ws=ws, asu=asu, br=br, adv=adv)
    })
    
    # ---- Print summary ----
    cat("=== Aggregate Across All Combats ===\n")
    cat("Average DPR per round:", mean(dprs), "\n")
    cat("Hit rate:", hits/attacks, "\n")
    cat("Crit rate:", crits/attacks, "\n")
    cat("Miss rate:", 1 - hits/attacks, "\n")
    cat("Average Guided Strikes used per day:", guided_uses, "\n")
    cat("Average War Priest bonus attacks used per day:", war_priest_uses, "\n")
    cat("Average Wrathful Smites used per day:", wrathful_uses, "\n")
    cat("Average Action Surges used per day:", action_surge_uses, "\n")
    cat("Share of Action Surges with Magic Weapon:", action_surge_with_magic_avg/action_surge_uses, "\n")
    cat("Average Brutality charges used per day:", brutality_uses, "\n")
    cat("Share of attacks made with advantage:", advantage_attacks/attacks, "\n\n")
    
    cat("=== Per-Combat Averages ===\n")
    
    # Combat 1
    cs1 <- combat_means[[1]]
    cat("Combat 1:\n")
    cat("  Avg Damage:", cs1$dmg/4, "\n")
    cat("  Avg Attacks:", cs1$att, "\n")
    cat("  Avg Hit Rate:", cs1$hits/cs1$att, "\n")
    cat("  Avg Crit Rate:", cs1$crits/cs1$att, "\n")
    cat("  Guided Strikes used:", cs1$gs, "\n")
    cat("  War Priest used:", cs1$wp, "\n")
    cat("  Wrathful Smites used:", cs1$ws, "\n")
    cat("  Action Surges used:", cs1$asu, "\n")
    cat("  Brutality used:", cs1$br, "\n")
    cat("  Share Attacks w/ advantage:", cs1$adv/cs1$att, "\n\n")
    
    # Combats 2 + 3 aggregated
    cs2 <- combat_means[[2]]
    cs3 <- combat_means[[3]]
    agg <- list(
      dmg   = cs2$dmg + cs3$dmg,
      att   = cs2$att + cs3$att,
      hits  = cs2$hits + cs3$hits,
      crits = cs2$crits + cs3$crits,
      gs    = cs2$gs + cs3$gs,
      wp    = cs2$wp + cs3$wp,
      ws    = cs2$ws + cs3$ws,
      asu   = cs2$asu + cs3$asu,
      br    = cs2$br + cs3$br,
      adv   = cs2$adv + cs3$adv
    )
    
    cat("Combats 2 + 3 (aggregated):\n")
    cat("  Avg Damage:", agg$dmg/8, "\n")  # divide by 8 rounds total (2 combats × 4 rounds)
    cat("  Avg Attacks:", agg$att/2, "\n") # average per combat
    cat("  Avg Hit Rate:", agg$hits/agg$att, "\n")
    cat("  Avg Crit Rate:", agg$crits/agg$att, "\n")
    cat("  Guided Strikes used:", agg$gs, "\n")
    cat("  War Priest used:", agg$wp, "\n")
    cat("  Wrathful Smites used:", agg$ws, "\n")
    cat("  Action Surges used:", agg$asu, "\n")
    cat("  Brutality used:", agg$br, "\n")
    cat("  Share Attacks w/ advantage:", agg$adv/agg$att, "\n\n")
    
    # Combat 4
    cs4 <- combat_means[[4]]
    cat("Combat 4:\n")
    cat("  Avg Damage:", cs4$dmg/4, "\n")
    cat("  Avg Attacks:", cs4$att, "\n")
    cat("  Avg Hit Rate:", cs4$hits/cs4$att, "\n")
    cat("  Avg Crit Rate:", cs4$crits/cs4$att, "\n")
    cat("  Guided Strikes used:", cs4$gs, "\n")
    cat("  War Priest used:", cs4$wp, "\n")
    cat("  Wrathful Smites used:", cs4$ws, "\n")
    cat("  Action Surges used:", cs4$asu, "\n")
    cat("  Brutality used:", cs4$br, "\n")
    cat("  Share Attacks w/ advantage:", cs4$adv/cs4$att, "\n\n")
  }
  
  # LEVEL 09 - 27.78 DPR 
  {
    rm(list=ls())
    set.seed(42)
    
    # Parameters
    rounds_per_combat <- 4
    combats <- 4
    combat_rounds <- rounds_per_combat * combats
    ac <- 16
    
    # Character parameters (level 9)
    cha_mod <- 5   # CHA 20
    prof_bonus <- 4
    dueling_bonus <- 2
    magic_bonus <- 1
    
    weapon_die <- 8
    true_strike_die <- 6
    wrathful_die <- 6
    
    # --- Damage functions ---
    weapon_dmg <- function(crit = FALSE, magic_active = FALSE) {
      dice <- if (crit) sample(1:weapon_die, 2, replace=TRUE) else sample(1:weapon_die, 1)
      dmg_bonus <- cha_mod + dueling_bonus + ifelse(magic_active, magic_bonus, 0)
      sum(dice) + dmg_bonus
    }
    true_strike_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:true_strike_die, 2, replace=TRUE) else sample(1:true_strike_die, 1)
      sum(dice)
    }
    wrathful_dmg <- function(crit = FALSE) {
      dice <- if (crit) sample(1:wrathful_die, 2, replace=TRUE) else sample(1:wrathful_die, 1)
      sum(dice)
    }
    
    # --- Attack roll with optional advantage ---
    attack_roll <- function(magic_active = FALSE, adv = FALSE) {
      if (adv) {
        rolls <- sample(1:20, 2, replace=TRUE)
        roll <- max(rolls)
      } else {
        roll <- sample(1:20, 1)
      }
      atk_bonus <- cha_mod + prof_bonus + ifelse(magic_active, magic_bonus, 0)
      list(roll = roll, total = roll + atk_bonus, crit = (roll == 20))
    }
    
    # Simulate one adventuring day
    simulate_day <- function() {
      # Resource pools (day-level)
      guided_left <- 2
      war_priest_charges <- 3
      wrathful_free <- 1
      cleric_slots <- 4
      pact_slots <- 1
      action_surge_left <- 1
      brutality_charges <- 5   # increased to 5 per short rest
      
      # Tracking (day-level)
      total_dmg <- 0
      total_attacks <- 0
      total_hits <- 0
      total_crits <- 0
      total_advantage_attacks <- 0
      
      guided_used_total <- 0
      war_priest_used_total <- 0
      wrathful_used_total <- 0
      action_surge_used_total <- 0
      action_surge_with_magic <- 0
      brutality_used_total <- 0
      
      # Per-combat tracking
      combat_stats <- list()
      
      # Randomly choose 2 combats for Magic Weapon
      magic_combats <- sample(1:combats, 2)
      
      for (combat in 1:combats) {
        magic_active <- combat %in% magic_combats
        vexed <- FALSE
        aoo_round <- sample(1:rounds_per_combat, 1)
        
        # Local counters
        dmg_c <- 0; att_c <- 0; hit_c <- 0; crit_c <- 0
        gs_c <- 0; wp_c <- 0; ws_c <- 0; as_c <- 0; br_c <- 0
        adv_c <- 0
        
        guided_used_in_combat <- FALSE
        ts_brutality_used <- 0   # track brutality uses in ts_only mode
        
        # Determine mode
        mode <- "setup"
        if (combat %in% c(2, 3)) {
          if (magic_active || (combat == 3 && war_priest_charges > 0)) {
            mode <- "setup"
          } else {
            mode <- "ts_only"
          }
        }
        if (combat == 4) mode <- "setup_any_gs"
        
        for (round in 1:rounds_per_combat) {

          # --- Action Surge on round 1 in setup modes ---
          if (round == 1 && mode != "ts_only") {
            if (action_surge_left > 0) {
              action_surge_left <- action_surge_left - 1
              action_surge_used_total <- action_surge_used_total + 1; as_c <- as_c + 1
              
              atk_as <- attack_roll(magic_active, adv = vexed)
              if (vexed) { adv_c <- adv_c + 1; total_advantage_attacks <- total_advantage_attacks + 1 }
              vexed <- FALSE
              att_c <- att_c + 1; total_attacks <- total_attacks + 1
              
              hit_as <- (atk_as$total >= ac) || atk_as$crit
              
              if (!hit_as && guided_left > 0) {
                if (combat == 1 && !guided_used_in_combat) {
                  hit_as <- TRUE
                  guided_left <- guided_left - 1
                  guided_used_total <- guided_used_total + 1
                  gs_c <- gs_c + 1
                  guided_used_in_combat <- TRUE
                } else if (combat != 1) {
                  hit_as <- TRUE
                  guided_left <- guided_left - 1
                  guided_used_total <- guided_used_total + 1
                  gs_c <- gs_c + 1
                }
              }
              
              if (hit_as) {
                hit_c <- hit_c + 1; total_hits <- total_hits + 1
                if (atk_as$crit) { crit_c <- crit_c + 1; total_crits <- total_crits + 1 }
                dmg_as <- weapon_dmg(atk_as$crit, magic_active)
                dmg_c <- dmg_c + dmg_as; total_dmg <- total_dmg + dmg_as
                if (brutality_charges > 0 && mode != "ts_only") {
                  brutality_charges <- brutality_charges - 1
                  brutality_used_total <- brutality_used_total + 1
                  br_c <- br_c + 1
                  vexed <- TRUE
                }
              }
              if (magic_active) action_surge_with_magic <- action_surge_with_magic + 1
            }
          }
          
          # --- War Priest on rounds 2-4 in setup modes ---
          if (mode != "ts_only" && round >= 2) {
            if (war_priest_charges > 0) {
              war_priest_charges <- war_priest_charges - 1
              war_priest_used_total <- war_priest_used_total + 1; wp_c <- wp_c + 1
              
              atk_wp <- attack_roll(magic_active, adv = vexed)
              if (vexed) { adv_c <- adv_c + 1; total_advantage_attacks <- total_advantage_attacks + 1 }
              vexed <- FALSE
              att_c <- att_c + 1; total_attacks <- total_attacks + 1
              
              hit_wp <- (atk_wp$total >= ac) || atk_wp$crit
              
              if (!hit_wp && guided_left > 0) {
                if (combat == 1 && !guided_used_in_combat) {
                  hit_wp <- TRUE
                  guided_left <- guided_left - 1
                  guided_used_total <- guided_used_total + 1
                  gs_c <- gs_c + 1
                  guided_used_in_combat <- TRUE
                } else if (combat != 1) {
                  hit_wp <- TRUE
                  guided_left <- guided_left - 1
                  guided_used_total <- guided_used_total + 1
                  gs_c <- gs_c + 1
                }
              }
              
              if (hit_wp) {
                hit_c <- hit_c + 1; total_hits <- total_hits + 1
                if (atk_wp$crit) { crit_c <- crit_c + 1; total_crits <- total_crits + 1 }
                dmg_wp <- weapon_dmg(atk_wp$crit, magic_active)
                dmg_c <- dmg_c + dmg_wp; total_dmg <- total_dmg + dmg_wp
                if (brutality_charges > 0 && mode != "ts_only") {
                  brutality_charges <- brutality_charges - 1
                  brutality_used_total <- brutality_used_total + 1
                  br_c <- br_c + 1
                  vexed <- TRUE
                }
              }
            }
          }
          
          # --- True Strike attack every round ---
          atk_ts <- attack_roll(magic_active, adv = vexed)
          if (vexed) { adv_c <- adv_c + 1; total_advantage_attacks <- total_advantage_attacks + 1 }
          vexed <- FALSE
          att_c <- att_c + 1; total_attacks <- total_attacks + 1
          
          hit_ts <- (atk_ts$total >= ac) || atk_ts$crit
          
          if (!hit_ts && guided_left > 0) {
            if (combat == 1 && !guided_used_in_combat && round >= 3) {
              hit_ts <- TRUE
              guided_left <- guided_left - 1
              guided_used_total <- guided_used_total + 1
              gs_c <- gs_c + 1
              guided_used_in_combat <- TRUE
            } else if (combat != 1) {
              hit_ts <- TRUE
              guided_left <- guided_left - 1
              guided_used_total <- guided_used_total + 1
              gs_c <- gs_c + 1
            }
          }
          
          # Wrathful smite logic
          add_wrathful <- FALSE
          if (mode == "ts_only") {
            if (wrathful_free > 0) { wrathful_free <- wrathful_free - 1; add_wrathful <- TRUE }
            else if (pact_slots > 0) { pact_slots <- pact_slots - 1; add_wrathful <- TRUE }
            else if (cleric_slots > 0) { cleric_slots <- cleric_slots - 1; add_wrathful <- TRUE }
          } else {
            if (round == 1) {
              if (pact_slots > 0) { pact_slots <- pact_slots - 1; add_wrathful <- TRUE }
              else if (cleric_slots > 0) { cleric_slots <- cleric_slots - 1; add_wrathful <- TRUE }
            }
          }
          if (add_wrathful) { 
            wrathful_used_total <- wrathful_used_total + 1
            ws_c <- ws_c + 1 
          }
          
          if (hit_ts) {
            hit_c <- hit_c + 1; total_hits <- total_hits + 1
            if (atk_ts$crit) { crit_c <- crit_c + 1; total_crits <- total_crits + 1 }
            dmg_ts <- weapon_dmg(atk_ts$crit, magic_active) + true_strike_dmg(atk_ts$crit)
            if (add_wrathful) dmg_ts <- dmg_ts + wrathful_dmg(atk_ts$crit)
            dmg_c <- dmg_c + dmg_ts; total_dmg <- total_dmg + dmg_ts
            
            # Brutality in ts_only mode: up to 2x per combat, only on rounds 1–3
            if (mode == "ts_only" && round <= 3 && ts_brutality_used < 2 && brutality_charges > 0) {
              brutality_charges <- brutality_charges - 1
              brutality_used_total <- brutality_used_total + 1
              br_c <- br_c + 1
              ts_brutality_used <- ts_brutality_used + 1
              vexed <- TRUE
            }
          }
          
          # --- AoO if this is the chosen round ---
          if (round == aoo_round) {
            atk_aoo <- attack_roll(magic_active, adv = vexed)
            if (vexed) { adv_c <- adv_c + 1; total_advantage_attacks <- total_advantage_attacks + 1 }
            vexed <- FALSE
            att_c <- att_c + 1; total_attacks <- total_attacks + 1
            
            hit_aoo <- (atk_aoo$total >= ac) || atk_aoo$crit
            
            if (!hit_aoo && guided_left > 0) {
              if (combat == 1 && !guided_used_in_combat && round >= 3) {
                hit_aoo <- TRUE
                guided_left <- guided_left - 1
                guided_used_total <- guided_used_total + 1
                gs_c <- gs_c + 1
                guided_used_in_combat <- TRUE
              } else if (combat != 1) {
                hit_aoo <- TRUE
                guided_left <- guided_left - 1
                guided_used_total <- guided_used_total + 1
                gs_c <- gs_c + 1
              }
            }
            
            if (hit_aoo) {
              hit_c <- hit_c + 1; total_hits <- total_hits + 1
              if (atk_aoo$crit) { crit_c <- crit_c + 1; total_crits <- total_crits + 1 }
              dmg_aoo <- weapon_dmg(atk_aoo$crit, magic_active)
              dmg_c <- dmg_c + dmg_aoo; total_dmg <- total_dmg + dmg_aoo
              
              # Brutality on AoO
              if (mode == "ts_only") {
                if (ts_brutality_used < 2 && brutality_charges > 0) {
                  brutality_charges <- brutality_charges - 1
                  brutality_used_total <- brutality_used_total + 1
                  br_c <- br_c + 1
                  ts_brutality_used <- ts_brutality_used + 1
                  vexed <- TRUE
                }
              } else if (brutality_charges > 0) {
                brutality_charges <- brutality_charges - 1
                brutality_used_total <- brutality_used_total + 1
                br_c <- br_c + 1
                vexed <- TRUE
              }
            }
          }
        } # end round loop
        
        # Resource recovery after combats 1 and 3
        if (combat == 1 || combat == 3) {
          guided_left <- min(2, guided_left + 1)
          war_priest_charges <- 3
          pact_slots <- 1
          action_surge_left <- 1
          brutality_charges <- 5   # reset to 5 per short rest
        }
        
        # Save per‑combat stats
        combat_stats[[combat]] <- list(
          dmg = dmg_c, att = att_c, hits = hit_c, crits = crit_c,
          gs = gs_c, wp = wp_c, ws = ws_c, `as` = as_c, br = br_c, adv = adv_c
        )
      } # end combat loop
      
      list(
        total_dpr = total_dmg / combat_rounds,
        total_attacks = total_attacks,
        total_hits = total_hits,
        total_crits = total_crits,
        guided_used = guided_used_total,
        war_priest_used = war_priest_used_total,
        wrathful_used = wrathful_used_total,
        action_surge_used = action_surge_used_total,
        action_surge_with_magic = action_surge_with_magic,
        brutality_used = brutality_used_total,
        advantage_attacks = total_advantage_attacks,
        combat_stats = combat_stats
      )
    }
    
    # Run simulation
    sims <- replicate(1000, simulate_day(), simplify=FALSE)
    
    # Aggregate totals
    dprs <- sapply(sims, function(x) x$total_dpr)
    attacks <- sum(sapply(sims, function(x) x$total_attacks))
    hits <- sum(sapply(sims, function(x) x$total_hits))
    crits <- sum(sapply(sims, function(x) x$total_crits))
    guided_uses <- mean(sapply(sims, function(x) x$guided_used))
    war_priest_uses <- mean(sapply(sims, function(x) x$war_priest_used))
    wrathful_uses <- mean(sapply(sims, function(x) x$wrathful_used))
    action_surge_uses <- mean(sapply(sims, function(x) x$action_surge_used))
    action_surge_with_magic_avg <- mean(sapply(sims, function(x) x$action_surge_with_magic))
    brutality_uses <- mean(sapply(sims, function(x) x$brutality_used))
    advantage_attacks <- sum(sapply(sims, function(x) x$advantage_attacks))
    
    # ---- Per-combat averages ----
    combat_means <- lapply(1:4, function(c) {
      dmg <- mean(sapply(sims, function(x) x$combat_stats[[c]]$dmg))
      att <- mean(sapply(sims, function(x) x$combat_stats[[c]]$att))
      hits <- mean(sapply(sims, function(x) x$combat_stats[[c]]$hits))
      crits <- mean(sapply(sims, function(x) x$combat_stats[[c]]$crits))
      gs <- mean(sapply(sims, function(x) x$combat_stats[[c]]$gs))
      wp <- mean(sapply(sims, function(x) x$combat_stats[[c]]$wp))
      ws <- mean(sapply(sims, function(x) x$combat_stats[[c]]$ws))
      asu <- mean(sapply(sims, function(x) x$combat_stats[[c]]$`as`))
      br <- mean(sapply(sims, function(x) x$combat_stats[[c]]$br))
      adv <- mean(sapply(sims, function(x) x$combat_stats[[c]]$adv))
      list(dmg=dmg, att=att, hits=hits, crits=crits,
           gs=gs, wp=wp, ws=ws, asu=asu, br=br, adv=adv)
    })
    
    # ---- Print summary ----
    cat("=== Aggregate Across All Combats ===\n")
    cat("Average DPR per round:", mean(dprs), "\n")
    cat("Hit rate:", hits/attacks, "\n")
    cat("Crit rate:", crits/attacks, "\n")
    cat("Miss rate:", 1 - hits/attacks, "\n")
    cat("Average Guided Strikes used per day:", guided_uses, "\n")
    cat("Average War Priest bonus attacks used per day:", war_priest_uses, "\n")
    cat("Average Wrathful Smites used per day:", wrathful_uses, "\n")
    cat("Average Action Surges used per day:", action_surge_uses, "\n")
    cat("Share of Action Surges with Magic Weapon:", action_surge_with_magic_avg/action_surge_uses, "\n")
    cat("Average Brutality charges used per day:", brutality_uses, "\n")
    cat("Share of attacks made with advantage:", advantage_attacks/attacks, "\n\n")
    
    cat("=== Per-Combat Averages ===\n")
    
    # Combat 1
    cs1 <- combat_means[[1]]
    cat("Combat 1:\n")
    cat("  Avg Damage:", cs1$dmg/4, "\n")
    cat("  Avg Attacks:", cs1$att, "\n")
    cat("  Avg Hit Rate:", cs1$hits/cs1$att, "\n")
    cat("  Avg Crit Rate:", cs1$crits/cs1$att, "\n")
    cat("  Guided Strikes used:", cs1$gs, "\n")
    cat("  War Priest used:", cs1$wp, "\n")
    cat("  Wrathful Smites used:", cs1$ws, "\n")
    cat("  Action Surges used:", cs1$asu, "\n")
    cat("  Brutality used:", cs1$br, "\n")
    cat("  Share Attacks w/ advantage:", cs1$adv/cs1$att, "\n\n")
    
    # Combats 2 + 3 aggregated
    cs2 <- combat_means[[2]]
    cs3 <- combat_means[[3]]
    agg <- list(
      dmg   = cs2$dmg + cs3$dmg,
      att   = cs2$att + cs3$att,
      hits  = cs2$hits + cs3$hits,
      crits = cs2$crits + cs3$crits,
      gs    = cs2$gs + cs3$gs,
      wp    = cs2$wp + cs3$wp,
      ws    = cs2$ws + cs3$ws,
      asu   = cs2$asu + cs3$asu,
      br    = cs2$br + cs3$br,
      adv   = cs2$adv + cs3$adv
    )
    
    cat("Combats 2 + 3 (aggregated):\n")
    cat("  Avg Damage:", agg$dmg/8, "\n")  # divide by 8 rounds total (2 combats × 4 rounds)
    cat("  Avg Attacks:", agg$att/2, "\n") # average per combat
    cat("  Avg Hit Rate:", agg$hits/agg$att, "\n")
    cat("  Avg Crit Rate:", agg$crits/agg$att, "\n")
    cat("  Guided Strikes used:", agg$gs, "\n")
    cat("  War Priest used:", agg$wp, "\n")
    cat("  Wrathful Smites used:", agg$ws, "\n")
    cat("  Action Surges used:", agg$asu, "\n")
    cat("  Brutality used:", agg$br, "\n")
    cat("  Share Attacks w/ advantage:", agg$adv/agg$att, "\n\n")
    
    # Combat 4
    cs4 <- combat_means[[4]]
    cat("Combat 4:\n")
    cat("  Avg Damage:", cs4$dmg/4, "\n")
    cat("  Avg Attacks:", cs4$att, "\n")
    cat("  Avg Hit Rate:", cs4$hits/cs4$att, "\n")
    cat("  Avg Crit Rate:", cs4$crits/cs4$att, "\n")
    cat("  Guided Strikes used:", cs4$gs, "\n")
    cat("  War Priest used:", cs4$wp, "\n")
    cat("  Wrathful Smites used:", cs4$ws, "\n")
    cat("  Action Surges used:", cs4$asu, "\n")
    cat("  Brutality used:", cs4$br, "\n")
    cat("  Share Attacks w/ advantage:", cs4$adv/cs4$att, "\n\n")
  }
  
  # LEVEL 10 - INCOMPLETE 
  {
    rm(list=ls())
    set.seed(42)
    
    # Parameters
    rounds_per_combat <- 4
    combats <- 4
    combat_rounds <- rounds_per_combat * combats
    ac <- 16
    
    # Character parameters (level 10)
    cha_mod <- 5   # CHA 20
    prof_bonus <- 4
    dueling_bonus <- 2
    magic_bonus <- 1
    
    # Dice parameters
    weapon_die <- 8
    wrathful_die <- 6
    
    # --- Attack roll with optional advantage ---
    # Returns the d20 roll, total vs AC, and crit flag.
    attack_roll <- function(magic_active = FALSE, adv = FALSE) {
      roll <- if (adv) max(sample(1:20, 2, replace = TRUE)) else sample(1:20, 1)
      atk_bonus <- cha_mod + prof_bonus + ifelse(magic_active, magic_bonus, 0)
      list(roll = roll, total = roll + atk_bonus, crit = (roll == 20))
    }
    
    # --- Weapon damage with optional wrathful integration ---
    # If wrathful_active = TRUE, add 1d6 to the attack's damage (Wrathful Smite).
    # On a crit, double ALL dice rolled (weapon dice and wrathful dice), but NOT modifiers.
    # Damage modifiers: CHA + Dueling + Magic Weapon (if active).
    weapon_dmg <- function(crit = FALSE, magic_active = FALSE, wrathful_active = FALSE) {
      # Base weapon dice: 1d8 (or 2d8 on crit)
      weapon_dice_count <- if (crit) 2 else 1
      weapon_rolls <- sample(1:weapon_die, weapon_dice_count, replace = TRUE)
      
      # Wrathful Smite dice: 1d6 (or 2d6 on crit) if active
      if (wrathful_active) {
        wrath_dice_count <- if (crit) 2 else 1
        wrath_rolls <- sample(1:wrathful_die, wrath_dice_count, replace = TRUE)
      } else {
        wrath_rolls <- 0
      }
      
      # Static damage bonus
      dmg_bonus <- cha_mod + dueling_bonus + ifelse(magic_active, magic_bonus, 0)
      
      sum(weapon_rolls) + sum(wrath_rolls) + dmg_bonus
    }
    
    
  }
  
}





      
