# war_angel_sim.R
# Phase 2: War Angel sim (levels 1–12) with full per‐level policies,
# correct AoO vs. monster AC, smite pools, rest rules, and guided‐strike gating.

library(data.table)
source("war_angel_phase1.R")   # must define make_actor(), attack_resolve(), logger, etc.

#—————————————————————————————————————————————————————————————
# 1) Proficiency bonus by character level
#—————————————————————————————————————————————————————————————
proficiency_by_level <- function(level) {
  if      (level <  5L)  2L
  else if (level <  9L)  3L
  else if (level < 13L)  4L
  else if (level < 17L)  5L
  else                   6L
}

#—————————————————————————————————————————————————————————————
# 2) Monster table loader and enemy attack phase function
#—————————————————————————————————————————————————————————————
monster_table <- NULL

set_monster_table <- function(df) {
  dt <- as.data.table(df)
  if (!all(c("level", "ac") %in% names(dt))) {
    stop("monster_table must include columns 'level' and 'ac'")
  }
  monster_table <<- dt
}

get_monster_row_for_level <- function(l) {
  if (is.null(monster_table)) return(list(ac = 15L, to_hit = 5L, attacks = 2L, dmg_on_hit = 6L))
  row <- monster_table[level == l][1]
  list(
    ac = as.integer(row$ac),
    to_hit = as.integer(row$to.hit.bonus),
    attacks = as.integer(row$att.per.round),
    dmg_on_hit = as.integer(row$dmg.on.hit)
  )
}

enemy_attack_phase <- function(actor, monster,
                               logger, round, combat,
                               p_target = 0.5) {
  # Each enemy attack has an independent probability p_target of targeting us.
  # Sap disadvantage is consumed on the *first enemy attack of the turn*,
  # regardless of whether that attack is directed at us.
  
  enemy_adv <- 0L
  parry_used <- 0L
  counter_used <- 0L
  sw_used <- 0L
  counter_dmg <- 0L
  adv_flag <- 0L
  
  for (i in seq_len(monster$attacks)) {
    # Apply Sap disadvantage to the *first* enemy attack of the turn
    if (i == 1L && !is.null(actor$statuses$enemy_sap)) {
      enemy_adv <- -1L
      actor$statuses$enemy_sap <- NULL  # consumed regardless of target
    } else {
      enemy_adv <- 0L
    }
    
    # Decide if this attack targets the War Angel
    if (runif(1) > p_target) {
      # Attack targets someone else → skip resolution
      next
    }
    
    # Enemy attack roll
    d20    <- roll_d20(enemy_adv)
    to_hit <- d20 + monster$to_hit
    
    # Effective AC (Shield of Faith adds +2 if active)
    eff_ac <- actor$ac + if (!is.null(actor$statuses$shield_of_faith)) 2L else 0L
    
    if (to_hit >= eff_ac && d20 != 1L) {
      # Check for use of flourish parry 
      if (actor$reaction && actor$use_flourish_parry == TRUE) {
        cha_mod <- actor$ability_mods$cha
        eff_ac_flourish <- eff_ac + max(1L, cha_mod)
        if (to_hit < eff_ac_flourish) {
          # Attack is parried + tracking 
          actor$reaction <- FALSE
          parry_used <- 1L
          logger$log(round, combat, actor$name, "Flourish Parry", d20, to_hit, FALSE, FALSE, 0L, "Enemy", "+CHA AC")
          # Counterattack specified by policy 
          if (actor$use_flourish_counter) {
            # expend flourish counter resources 
            if (actor$resources$`Free Counter`$charges>0){
              actor$resources$`Free Counter`$charges <- actor$resources$`Free Counter`$charges - 1L
            } else {
              actor$resources$`Second Wind`$charges <- actor$resources$`Second Wind`$charges - 1L
              sw_used <- 1L
            }
            # determine if we have advantage from vex and, if so, consume it
            if (!is.null(actor$statuses$vex)) {
              adv_flag <- 1L
              actor$statuses$vex <- NULL
            } else {
              adv_flag <- 0L
            }
            # make counter attack and track 
            res <- attack_resolve(actor, monster$ac, adv=adv_flag) 
            counter_used <- 1L
            if (res$hit) {
              # Apply specified brutality effect without spending a charge
              if (actor$flourish_brutality=="Bluff"){
                actor$statuses$vex <- list(duration=1L)
                actor$statuses$brutality_save_adv <- list(duration=2L)
              }
              if (actor$flourish_brutality=="Bleed"){
                actor$statuses$enemy_sap <- list(pending = TRUE)
                res$damage <- res$damage + max(1L, cha_mod)
              }
              # track counter damage 
              counter_dmg <- counter_dmg + res$damage
              # Apply vex/sap based on weapon mastery 
              if (identical(actor$weapon$mastery, "vex")) {actor$statuses$vex <- list(duration = 1L)}
              if (identical(actor$weapon$mastery, "sap")) {actor$statuses$enemy_sap <- list(pending = TRUE)}
            }
            logger$log(round, combat, actor$name, "Flourish Counter", res$roll, res$to_hit, res$hit, res$crit,
                       if (res$hit) res$damage else 0L, "Enemy", res$notes)
          }
          next  # skip damage from the enemy attack
        }
      }
      # if not parried, take/track damage as normal 
      actor$hp <- max(0L, actor$hp - monster$dmg_on_hit)
      actor$enemy_dmg_total <- actor$enemy_dmg_total + monster$dmg_on_hit
      
      # Concentration check if concentrating
      if (!is.null(actor$concentration_spell)) {
        actor$conc_checks <- actor$conc_checks + 1L
        dc <- max(10L, floor(monster$dmg_on_hit / 2L))
        
        # Advantage if brutality save rider is active (and consume on use)
        adv <- if (!is.null(actor$statuses$brutality_save_adv)) 1L else 0L
        bless_active <- (actor$concentration_spell == "bless")
        
        sv <- roll_save(base_mod = actor$save_mods$con,
                        adv = adv,
                        bless_active = bless_active)
        
        # consume brutality save advantage if present
        if (!is.null(actor$statuses$brutality_save_adv)) {
          actor$statuses$brutality_save_adv <- NULL
        }
        
        if (sv$total < dc) {
          # Lose concentration
          actor$concentration_spell <- NULL
          actor$statuses$bless_conc <- NULL
          actor$conc_fails <- actor$conc_fails + 1L
        }
      }
    }
  }
  
  list(actor=actor, 
       adv_flag=adv_flag,
       parry_used = parry_used,
       counter_used = counter_used,
       sw_used = sw_used,
       counter_dmg = counter_dmg)
}

#—————————————————————————————————————————————————————————————
# 3) Short/Long Rest overrides
#—————————————————————————————————————————————————————————————
recharge_short <- function(actor) {
  for (nm in names(actor$resources)) {
    r <- actor$resources[[nm]]
    # Fully recover these on a short rest:
    if (nm %in% c("Pact Slot", "War Priest", "Action Surge", "Brutality") &&
        r$recharge$short) {
      actor$resources[[nm]]$charges <- r$max
    }
    # Channel Divinity gains +1 charge (capped)
    if (nm %in% c("Channel Divinity","Second Wind") && r$recharge$short) {
      actor$resources[[nm]]$charges <-
        pmin(r$max, r$charges + 1L)
    }
  }
  actor
}

recharge_long <- function(actor) {
  for (nm in names(actor$resources)) {
    r <- actor$resources[[nm]]
    if (r$recharge$long) {
      actor$resources[[nm]]$charges <- r$max
    }
  }
  actor
}

#—————————————————————————————————————————————————————————————
# 4) Actor factory (up to level 20)
#—————————————————————————————————————————————————————————————
create_war_angel <- function(level) {
  prof    <- proficiency_by_level(level)
  hp      <- 50L
  ac      <- 18L
  
  # Ability modifiers
  str_mod <- -1L
  int_mod <- -1L
  con_mod <- -1L
  wis_mod <- 3L
  cha_mod <- if (level <  6L) 3L
  else if (level <  9L) 4L
  else                  5L
  dex_mod <- if (level < 11L) 2L
  else if (level < 19L) 3L
  else                  4L
  
  # Saving throws 
  str_save <- str_mod + prof
  dex_save <- if (level < 15L) dex_mod else dex_mod + prof
  con_save <- con_mod + prof
  int_save <- int_mod
  wis_save <- wis_mod
  cha_save <- cha_mod

  # Resource pools by level
  cler1    <- if (level <= 2L) 0L else if (level == 3) 2L else if (level == 4) 3L else if (level >=5) 4L
  cler2    <- if (level <= 4L) 0L else if (level >= 5) 2L
  cler3    <- if (level <= 11) 0L else if (level == 12) 2L else if (level >= 13) 3L
  cler4    <- if (level <  20) 0L else 1L
  pact1    <- if (level >= 2L) 1L else 0L
  free1    <- if (level >= 6L) 1L else 0L
  divinity_cd <- if (level < 4L) 0L else if (level >=4 && level < 13) 2L else if (level >= 13) 3L
  wp_cd    <- if (level >= 5L) 3L else 0L
  surge_cd <- if (level >= 7L) 1L else 0L
  brut_cd  <- if (level == 8L) 4L else if (level >= 9L) 5L else 0L
  sw_cd    <- if (level < 9L) 2L else if (level >=9 && level < 17) 3L else if (level >= 17) 4L
  flourish <- if (level >= 14L) 1L else 0L
  
  resources <- list(
    `Smite Free`    = make_resource("Smite Free",    free1,    rec_short=FALSE, rec_long=TRUE),
    `Pact Slot`     = make_resource("Pact Slot",     pact1,    rec_short=TRUE,  rec_long=TRUE),
    `Cleric Slot1`  = make_resource("Cleric Slot1",  cler1,    rec_short=FALSE, rec_long=TRUE),
    `Cleric Slot2`  = make_resource("Cleric Slot2",  cler2,    rec_short=FALSE, rec_long=TRUE),
    `Cleric Slot3`  = make_resource("Cleric Slot3",  cler3,    rec_short=FALSE, rec_long=TRUE),
    `Cleric Slot4`  = make_resource("Cleric Slot4",  cler4,    rec_short=FALSE, rec_long=TRUE),
    `Channel Divinity` = make_resource("Channel Divinity", divinity_cd, rec_short=TRUE, rec_long=TRUE),
    `War Priest`    = make_resource("War Priest",    wp_cd,    rec_short=TRUE,  rec_long=TRUE),
    `Action Surge`  = make_resource("Action Surge",  surge_cd, rec_short=TRUE,  rec_long=TRUE),
    `Brutality`     = make_resource("Brutality",     brut_cd,  rec_short=TRUE,  rec_long=TRUE),
    `Second Wind`   = make_resource("Second Wind",   sw_cd,    rec_short=TRUE,  rec_long=TRUE),
    `Free Counter`  = make_resource("Free Counter",  flourish, rec_short=FALSE, rec_long=TRUE)
  )
  
  if (level == 1L) {
    weapon <- make_weapon(
      name        = "Rapier",
      n_dice      = 1L,
      die_size    = 8L,
      dmg_mod     = dex_mod + 2L,
      mastery     = "vex",
      attack_stat = "dex"
    )
  }
  else if (level > 1L && level < 16L) {
    weapon <- make_weapon(
      name        = "Longsword",
      n_dice      = 1L,
      die_size    = 8L,
      dmg_mod     = cha_mod + 2L,
      mastery     = "sap",
      attack_stat = "cha"
    )
  }
  else {
    weapon <- make_weapon(
      name        = "Rapier",
      n_dice      = 1L,
      die_size    = 8L,
      dmg_mod     = cha_mod + 2L,
      mastery     = "vex",
      attack_stat = "cha"
    )
  }
  
  make_actor(
    name         = paste0("War Angel L", level),
    level        = level,
    hp           = hp,
    ac           = ac,
    prof         = prof,
    ability_mods = list(
      str = str_mod,
      dex = dex_mod,
      con = con_mod,
      int = int_mod,
      wis = wis_mod,
      cha = cha_mod
    ),
    save_mods = list( 
      str = str_save,
      dex = dex_save,
      con = con_save,
      int = int_save,
      wis = wis_save,
      cha = cha_save
    ),
    weapon    = weapon,
    resources = resources,
    statuses  = list()
  )
}

#—————————————————————————————————————————————————————————————
# 5) Per‐level combat policy (up to level 13)
#—————————————————————————————————————————————————————————————
policy_per_level <- function(actor, level, combat, round) {
  # Unpack remaining resources
  rp     <- actor$resources$`War Priest`$charges
  ra     <- actor$resources$`Action Surge`$charges
  rf     <- actor$resources$`Smite Free`$charges
  rpact  <- actor$resources$`Pact Slot`$charges
  rg     <- actor$resources$`Channel Divinity`$charges
  rg_max <- actor$resources$`Channel Divinity`$max
  rb     <- actor$resources$Brutality$charges
  mb     <- as.integer(actor$magic_weapon_bonus)
  sw     <- actor$resources$`Second Wind`$charges
  sw_max <- actor$resources$`Second Wind`$max
  fc     <- actor$resources$`Free Counter`$charges
  # discrete cleric slots + safe total
  rclr1 <- as.integer(actor$resources$`Cleric Slot1`$charges)
  rclr2 <- as.integer(actor$resources$`Cleric Slot2`$charges)
  rclr3 <- as.integer(actor$resources$`Cleric Slot3`$charges)
  rclr_total <- (if (is.na(rclr1)) 0L else rclr1) +
                (if (is.na(rclr2)) 0L else rclr2) +
                (if (is.na(rclr3)) 0L else rclr3)
  
  # Initialize default decision flags
  dec <- list(
    use_true_strike      = FALSE,
    n_action_surge       = 0L,
    use_guided_strike    = FALSE,
    brutality_spend      = 0L,
    use_smite            = FALSE,
    prefer_smite_on_crit = FALSE,
    use_war_priest       = FALSE,
    guided_strike_aoo    = FALSE,
    cast_bless_round1    = FALSE,
    use_shield_of_faith  = FALSE,
    use_flourish_parry   = FALSE,
    use_flourish_counter = FALSE,
    flourish_brutality   = "Bluff" # Bleed
  )
  if (level == 6L){dec$guided_strike_aoo = TRUE}
  if (level == 7L){dec$guided_strike_aoo = FALSE}
  if (level == 8L){dec$guided_strike_aoo = TRUE}
  if (level >= 9L){dec$guided_strike_aoo = TRUE}
  
  # LEVEL 1: rapier only
  if (level == 1L) return(dec)
  
  # LEVELS 2–4: longsword only
  if (level %in% 2:4) return(dec)
  
  # LEVEL 5: True‐Strike + War Priest + GS when charges remain
  if (level == 5L) {
    dec$use_true_strike    <- TRUE
    if (rg > 0L)   dec$use_guided_strike <- TRUE
    if (rp > 0L)   dec$use_war_priest    <- TRUE
    return(dec)
  }
  
  # LEVEL 6: add Wrathful Smite + GS gating (once in C1, any miss C2–4)
  if (level == 6L) {
    dec$use_true_strike <- TRUE
    if ((combat == 1L && rg == rg_max) ||
        (combat > 1L && rg > 0L)) {
      dec$use_guided_strike <- TRUE
    }
    if (combat == 1L) {
      if (round == 1L) dec$use_smite <- (rpact > 0L)
      else             dec$use_war_priest <- (rp > 0L)
    }
    else if (combat == 2L) {
      if ((mb > 0L && level <=11) || (mb > 1L && level > 11)) {
        if (round == 1L) dec$use_smite <- (rpact > 0L)
        else {
          dec$use_war_priest       <- (rp > 0L)
          dec$prefer_smite_on_crit <- TRUE
        }
      } else {
        dec$use_smite <- (rpact + rf + rclr_total) > 0L
      }
    }
    else if (combat %in% 3:4) {
      if (rp > 0L) {
        dec$use_war_priest       <- TRUE
        dec$prefer_smite_on_crit <- TRUE
      } else {
        dec$use_smite <- (rpact + rf + rclr_total) > 0L
      }
    }
    return(dec)
  }
  
  # LEVEL 7: adds Action Surge + same GS gating as L6
  if (level == 7L) {
    dec$use_true_strike <- TRUE
    if ((combat == 1L && rg == rg_max) ||
        (combat > 1L && rg > 0L)) {
      dec$use_guided_strike <- TRUE
    }
    if (combat == 1L) {
      if (ra > 0L && round == 1L) dec$n_action_surge <- 1L
      if (round == 1L)            dec$use_smite       <- (rpact > 0L)
      if (round > 1L)             dec$use_war_priest  <- (rp > 0L)
    }
    else if (combat == 2L) {
      if (((mb > 0L && level <=11) || (mb > 1L && level > 11)) && ra > 0L && round == 1L) {
        dec$n_action_surge <- 1L
      }
      if ((mb > 0L && level <=11) || (mb > 1L && level > 11)) {
        if (round == 1L) dec$use_smite <- (rpact > 0L)
        else {
          dec$use_war_priest       <- (rp > 0L)
          dec$prefer_smite_on_crit <- TRUE
        }
      } else {
        dec$use_smite <- (rpact + rf + rclr_total ) > 0L
      }
    }
    else if (combat %in% 3:4) {
      if (ra > 0L && round == 1L) dec$n_action_surge <- 1L
      if (rp > 0L) {
        dec$use_war_priest       <- TRUE
        dec$prefer_smite_on_crit <- TRUE
      } else {
        dec$use_smite <- (rpact + rf + rclr_total) > 0L
      }
    }
    return(dec)
  }
  
  # LEVEL 8: setup‐first order + Brutality + GS gating
  if (level == 8L) {
    dec$use_true_strike <- TRUE
    
    # COMBAT 1: GS once per combat on setup attacks R1–2; rounds 3–4 any miss
    if (combat == 1L) {
      if (round == 1L) {
        if (ra > 0L)     dec$n_action_surge  <- 1L
        if (rb > 0L)     dec$brutality_spend <- 1L
        dec$use_smite    <- (rpact > 0L)
        if (rg == rg_max) dec$use_guided_strike <- TRUE
      }
      else if (round == 2L) {
        if (rp > 0L) {
          dec$use_war_priest  <- TRUE
          if (rb > 0L)        dec$brutality_spend <- 1L
        }
        if (rg == rg_max)    dec$use_guided_strike <- TRUE
      }
      else {
        if (rp > 0L) {
          dec$use_war_priest  <- TRUE
          if (rb > 0L)        dec$brutality_spend <- 1L
        }
        if (round >= 3L && rg == rg_max) {
          dec$use_guided_strike <- TRUE
        }
      }
      return(dec)
    }
    
    # COMBAT 2:
    if (combat == 2L) {
      if ((mb > 0L && level <=11) || (mb > 1L && level > 11)) {
        # magic weapon: same setup‐vs‐later + GS per turn; Brutality on rounds 1–4 setup attacks
        if (round == 1L) {
          if (ra > 0L)     dec$n_action_surge  <- 1L
          if (rb > 0L)     dec$brutality_spend <- 1L
          dec$use_smite    <- (rpact > 0L)
        } else {
          if (rp > 0L) {
            dec$use_war_priest  <- TRUE
            if (rb > 0L)        dec$brutality_spend <- 1L
          }
        }
        if (round <= 2L &&
            ((round == 1L && dec$n_action_surge > 0L) ||
             (round == 2L && dec$use_war_priest))) {
          dec$use_guided_strike <- (rg > 0L)
        } else {
          dec$use_guided_strike <- (rg > 0L)
        }
      } else {
        # no magic weapon: True‐Strike + Smite each round; no Brutality; GS once/comb
        dec$use_smite <- (rpact + rf + rclr_total) > 0L
        if (rg == rg_max) dec$use_guided_strike <- TRUE
      }
      return(dec)
    }
    
    # COMBAT 3:
    if (combat == 3L) {
      if (ra > 0L && round == 1L) {
        dec$n_action_surge  <- 1L
        if (rb > 0L)        dec$brutality_spend <- 1L
        dec$use_smite       <- (rpact > 0L)
      }
      else if (rp > 0L) {
        dec$use_war_priest  <- TRUE
        if (rb > 0L)        dec$brutality_spend <- 1L
      }
      else {
        dec$use_smite       <- (rpact + rf + rclr_total) > 0L
        if (rb > 0L)        dec$brutality_spend <- 1L
      }
      if (rg > 0L)          dec$use_guided_strike <- TRUE
      return(dec)
    }
    
    # COMBAT 4:
    if (combat == 4L) {
      if (round == 1L) {
        if (ra > 0L)     dec$n_action_surge  <- 1L
        if (rb > 0L)     dec$brutality_spend <- 1L
        dec$use_smite    <- (rpact > 0L)
      } else {
        if (rp > 0L) {
          dec$use_war_priest  <- TRUE
          if (rb > 0L)        dec$brutality_spend <- 1L
        }
      }
      if (rg > 0L)          dec$use_guided_strike <- TRUE
      return(dec)
    }
  }
  
  # LEVEL 9: same as L8, but C2 without +1 weapon spends up to 2 Brutality charges/comb
  if (level == 9L) {
    dec$use_true_strike <- TRUE
    
    # COMBAT 1: identical to L8 C1
    if (combat == 1L) {
      if (round == 1L) {
        if (ra > 0L)        dec$n_action_surge    <- 1L
        if (rb > 0L)        dec$brutality_spend   <- 1L
        dec$use_smite       <- (rpact > 0L)
        if (rg == rg_max)   dec$use_guided_strike <- TRUE
      }
      else if (round == 2L) {
        if (rp > 0L) {
          dec$use_war_priest  <- TRUE
          if (rb > 0L)        dec$brutality_spend <- 1L
        }
        if (rg == rg_max)   dec$use_guided_strike <- TRUE
      }
      else {
        if (rp > 0L) {
          dec$use_war_priest  <- TRUE
          if (rb > 0L)        dec$brutality_spend <- 1L
        }
        if (round >= 3L && rg == rg_max) {
          dec$use_guided_strike <- TRUE
        }
      }
      return(dec)
    }
    
    # COMBAT 2
    if (combat == 2L) {
      if ((mb > 0L && level <=11) || (mb > 1L && level > 11)) {
        # magic weapon: mirror L8 logic
        if (round == 1L) {
          if (ra > 0L)      dec$n_action_surge    <- 1L
          if (rb > 0L)      dec$brutality_spend   <- 1L
          dec$use_smite     <- (rpact > 0L)
        } else {
          if (rp > 0L) {
            dec$use_war_priest  <- TRUE
            if (rb > 0L)        dec$brutality_spend <- 1L
          }
        }
        if (round <= 2L &&
            ((round == 1L && dec$n_action_surge > 0L) ||
             (round == 2L && dec$use_war_priest))) {
          dec$use_guided_strike <- (rg > 0L)
        } else {
          dec$use_guided_strike <- (rg > 0L)
        }
      } else {
        # no magic weapon: True‐Strike + Smite each round
        dec$use_smite <- (rpact + rf + rclr_total) > 0L
        
        # Burn 1 Brutality charge/turn until 2 total used this combat
        # COULD UPDATE TO PROHIBIT USE ON ROUND 4
        used_brutality <- actor$resources$Brutality$max - rb
        if (rb > 0L && used_brutality < 2L) {
          dec$brutality_spend <- 1L
        }
        
        # GS once per combat
        if (rg == rg_max) {
          dec$use_guided_strike <- TRUE
        }
      }
      return(dec)
    }
    
    # COMBAT 3:
    if (combat == 3L) {
      if (ra > 0L && round == 1L) {
        dec$n_action_surge    <- 1L
        if (rb > 0L)          dec$brutality_spend   <- 1L
        dec$use_smite         <- (rpact > 0L)
      }
      else if (rp > 0L) {
        dec$use_war_priest    <- TRUE
        if (rb > 0L)          dec$brutality_spend   <- 1L
      }
      else {
        dec$use_smite         <- (rpact + rf + rclr_total) > 0L
        if (rb > 0L)          dec$brutality_spend   <- 1L
      }
      # GS once per turn on any miss
      if (rg > 0L)           dec$use_guided_strike <- TRUE
      return(dec)
    }
    
    # COMBAT 4:
    if (combat == 4L) {
      if (round == 1L) {
        if (ra > 0L)        dec$n_action_surge    <- 1L
        if (rb > 0L)        dec$brutality_spend   <- 1L
        dec$use_smite       <- (rpact > 0L)
      }
      else {
        if (rp > 0L) {
          dec$use_war_priest  <- TRUE
          if (rb > 0L)        dec$brutality_spend <- 1L
        }
      }
      if (rg > 0L)           dec$use_guided_strike <- TRUE
      return(dec)
    }
  }
  
  # LEVELS 10-11: extra attack and revised resource gating
  # LEVEL 12: same as level 10-11, but with upcast magic weapon 
  if (level %in% 10:12){
    # defaults
    dec$use_true_strike <- FALSE 
    dec$n_action_surge <- 0L
    dec$use_war_priest <- FALSE
    dec$use_smite      <- FALSE
    dec$prefer_smite_on_crit <- FALSE
    dec$brutality_spend <- 0L
    
    # COMBAT 1 
    if (combat == 1L) {
      if (round == 1L) {
        if (ra > 0L)        dec$n_action_surge    <- 1L
        if (rb > 0L)        dec$brutality_spend   <- 1L
        dec$use_smite       <- (rpact > 0L)
        if (rg == rg_max)   dec$use_guided_strike <- TRUE
      }
      else if (round == 2L) {
        if (rp > 0L) {
          dec$use_war_priest  <- TRUE
          if (rb > 0L)        dec$brutality_spend <- 1L
        }
        if (rg == rg_max)   dec$use_guided_strike <- TRUE
      }
      else {
        if (rp > 0L) {
          dec$use_war_priest  <- TRUE
          if (rb > 0L)        dec$brutality_spend <- 1L
        }
        if (round >= 3L && rg == rg_max) {
          dec$use_guided_strike <- TRUE
        }
      }
      return(dec)
    }
    
    # COMBAT 2
    if (combat == 2L) {
      dec$prefer_smite_on_crit <- TRUE
      if ((mb > 0L && level <=11) || (mb > 1L && level > 11)) {
        # magic weapon: mirror L9 logic
        dec$use_guided_strike <- (rg > 0L)
        if (round == 1L) {
          if (ra > 0L)      dec$n_action_surge    <- 1L
          if (rb > 0L)      dec$brutality_spend   <- 1L
          dec$use_smite     <- (rpact > 0L)
        } else {
          if (rp > 0L) {
            dec$use_war_priest  <- TRUE
            if (rb > 0L)        dec$brutality_spend <- 1L
          }
        }
      } else {
        # no magic weapon: attack + Smite each round
        dec$use_smite <- (rpact + rf + rclr_total) > 0L
        
        # Burn 1 Brutality charge/turn until 2 total used this combat
        used_brutality <- actor$resources$Brutality$max - rb
        if (rb > 0L && used_brutality < 2L) {
          dec$brutality_spend <- 1L
        }
        
        # GS once per turn on any miss
        if (rg > 0L)           dec$use_guided_strike <- TRUE
      }
      return(dec)
    }
    
    # COMBAT 3:
    if (combat == 3L) {
      dec$prefer_smite_on_crit <- TRUE
      if (ra > 0L && round == 1L) {
        dec$n_action_surge    <- 1L
        if (rb > 0L)          dec$brutality_spend   <- 1L
        dec$use_smite         <- (rpact > 0L)
      }
      else if (rp > 0L) {
        dec$use_war_priest    <- TRUE
        if (rb > 0L)          dec$brutality_spend   <- 1L
      }
      else {
        dec$use_smite         <- (rpact + rf + rclr_total) > 0L
        if (rb > 0L)          dec$brutality_spend   <- 1L
      }
      # GS once per turn on any miss
      if (rg > 0L)           dec$use_guided_strike <- TRUE
      return(dec)
    }
    
    # COMBAT 4:
    if (combat == 4L) {
      if (round == 1L) {
        if (ra > 0L)        dec$n_action_surge    <- 1L
        if (rb > 0L)        dec$brutality_spend   <- 1L
        dec$use_smite       <- (rpact > 0L)
      }
      else {
        if (rp > 0L) {
          dec$use_war_priest  <- TRUE
          if (rb > 0L)        dec$brutality_spend <- 1L
        }
      }
      if (rg > 0L)           dec$use_guided_strike <- TRUE
      return(dec)
    }
  }
  
  # LEVEL 13: Bless + Shield of Faith, revised GS/wrathful smite 
  if (level == 13L) {
    # initialize defaults
    dec$use_true_strike      <- FALSE
    dec$n_action_surge       <- 0L
    dec$use_guided_strike    <- FALSE
    dec$brutality_spend      <- 1L   # default: spend on first hit each round
    dec$use_smite            <- FALSE
    dec$prefer_smite_on_crit <- FALSE
    dec$use_war_priest       <- FALSE
    dec$guided_strike_aoo    <- FALSE
    dec$cast_bless_round1    <- FALSE
    dec$use_shield_of_faith  <- FALSE
    
    # Round 1: always cast Bless and Shield of Faith
    if (round == 1L) {
      dec$cast_bless_round1   <- TRUE
      dec$use_shield_of_faith <- TRUE
      
      # Action Surge conditions
      if (combat == 1L || combat == 4L ||
          (combat == 2L && mb >= 2L) ||
          (combat == 3L && ra > 0L)) {
        dec$n_action_surge <- 1L
      }
    }
    
    # Guided Strike gating
    if (combat == 1L) {
      if (rg == rg_max)  dec$use_guided_strike <- TRUE
    } else if (combat == 2L) {
      if (rg >= 2L) dec$use_guided_strike <- TRUE
    } else if (combat %in% 3:4) {
      if (rg > 0L) dec$use_guided_strike <- TRUE
    }
    
    # Rounds 2–4: attack actions
    if (round %in% 2:4) {
      if (combat %in% c(1L, 4L) || (combat == 2L && mb >= 2L)) {
        if (rp > 0L) dec$use_war_priest <- TRUE
      }
      if (combat == 2L && mb == 1L) {
        # Wrathful Smite BA instead of War Priest
        dec$use_smite <- (rpact + rf + rclr_total) > 0L
        # Brutality limited to 2 per combat
        used_brutality <- actor$resources$Brutality$max - rb
        if (used_brutality >= 2L) dec$brutality_spend <- 0L
      }
      if (combat == 3L) {
        if (rp > 0L) {
          dec$use_war_priest <- TRUE
        } else {
          dec$use_smite <- (rpact + rf + rclr_total) > 0L
        }
      }
    }
    
    return(dec)
  }
  
  # LEVELS 14-15: Same as 13 but with flourish counter (bleed)
  if (level == 14L | level == 15) {
    # initialize defaults
    dec$use_true_strike      <- FALSE
    dec$n_action_surge       <- 0L
    dec$use_guided_strike    <- FALSE
    dec$brutality_spend      <- 1L   # default: spend on first hit each round
    dec$use_smite            <- FALSE
    dec$prefer_smite_on_crit <- FALSE
    dec$use_war_priest       <- FALSE
    dec$guided_strike_aoo    <- FALSE
    dec$cast_bless_round1    <- FALSE
    dec$use_shield_of_faith  <- FALSE
    dec$use_flourish_parry   <- TRUE
    dec$use_flourish_counter <- TRUE
    dec$flourish_brutality   <- "Bleed" # Bluff
      
    # Round 1: always cast Bless and Shield of Faith
    if (round == 1L) {
      dec$cast_bless_round1   <- TRUE
      dec$use_shield_of_faith <- TRUE
      
      # Action Surge conditions
      if (combat == 1L || combat == 4L ||
          (combat == 2L && mb >= 2L) ||
          (combat == 3L && ra > 0L)) {
        dec$n_action_surge <- 1L
      }
    }
    
    # Guided Strike gating
    if (combat == 1L) {
      if (rg == rg_max)  dec$use_guided_strike <- TRUE
    } else if (combat == 2L) {
      if (rg >= 2L) dec$use_guided_strike <- TRUE
    } else if (combat %in% 3:4) {
      if (rg > 0L) dec$use_guided_strike <- TRUE
    }
    
    # Rounds 2–4: attack actions
    if (round %in% 2:4) {
      if (combat %in% c(1L, 4L) || (combat == 2L && mb >= 2L)) {
        if (rp > 0L) dec$use_war_priest <- TRUE
      }
      if (combat == 2L && mb == 1L) {
        # Wrathful Smite BA instead of War Priest
        dec$use_smite <- (rpact + rf + rclr_total) > 0L
        # Brutality limited to 2 per combat
        used_brutality <- actor$resources$Brutality$max - rb
        if (used_brutality >= 2L) dec$brutality_spend <- 0L
      }
      if (combat == 3L) {
        if (rp > 0L) {
          dec$use_war_priest <- TRUE
        } else {
          dec$use_smite <- (rpact + rf + rclr_total) > 0L
        }
      }
    }
    
    # Flourish counter gating 
      # Only use free charge in combat 1 
      # Use up to once in combats 2 and 3 
      # Use up to once in combat 4 
      # use sw_max to control gating in combats 2,3,4 
    if (combat==1 && fc==0){dec$use_flourish_counter <- FALSE}
    if (combat %in% c(2,3,4) && sw < sw_max){dec_use_flourish_counter <- FALSE}
    
    return(dec)
  }
  
}

#—————————————————————————————————————————————————————————————
# 6) AoO resolver
#—————————————————————————————————————————————————————————————
resolve_aoo <- function(actor,
                        logger,
                        combat,
                        round,
                        defender_ac,
                        guided_strike_allowed = FALSE) {
  if (!actor$reaction) return(list(actor=actor, 
                                   adv_flag=0L,
                                   damage   = 0L
  ))
  
  # Determine if vex grants advantage, consume it
  if (!is.null(actor$statuses$vex)) {
      adv_flag <- 1L
      actor$statuses$vex <- NULL
      } else {
      adv_flag <- 0L
  }
    
  # roll the AoO attack
  res <- attack_resolve(
    actor,
    defender_ac,
    adv       = adv_flag
  )
  actor <- res$attacker
  actor$reaction <- FALSE
  
  gs_used <- 0L
  # Optionally allow Guided Strike on AoO (uses same gating as other attacks)
  if (!res$hit &&
      res$roll != 1L &&
      guided_strike_allowed &&
      !is.null(actor$resources$`Channel Divinity`) &&
      actor$resources$`Channel Divinity`$charges > 0L &&
      (res$to_hit + 10L) >= defender_ac) {
        # spend the charge and mark GS used
        actor$resources$`Channel Divinity`$charges <- actor$resources$`Channel Divinity`$charges - 1L
        gs_used <- 1L
        # force to hit and re-roll damage same as other GS logic
        res$to_hit <- res$to_hit + 10L
        res$hit    <- TRUE
        dice_n <- if (res$crit) actor$weapon$n_dice * 2L else actor$weapon$n_dice
        res$damage <- roll_dice(dice_n, actor$weapon$die_size) +
                      actor$weapon$dmg_mod +
                      as.integer(actor$magic_weapon_bonus)
  }
  
  # unpack resources and state
  rb        <- actor$resources$Brutality$charges
  ra        <- actor$resources$`Action Surge`$charges
  max_rb    <- actor$resources$Brutality$max
  used_rb   <- max_rb - rb
  lvl       <- actor$level
  mb        <- as.integer(actor$magic_weapon_bonus)
  
  # determine if we should burn Brutality on this AoO hit
  brut_used <- 0L 
  do_brut <- res$hit &&
    rb > 0L &&
    (
      # always in C1 or C4
      combat %in% c(1L, 4L)
      ||
        # in C2 if magic weapon
        (combat == 2L && ((mb > 0L && lvl <=11) || (mb > 1L && lvl > 11)))
      ||
        # in C2 at level 9 without magic weapon, up to 2 charges
        (combat == 2L &&
           lvl == 9L &&
           ((mb > 0L && lvl <=11) || (mb > 1L && lvl > 11)) &&
           used_rb < 2L)
      ||
        # in C3 if Surge remains or Brutality remains
        (combat == 3L && (ra > 0L || rb > 0L))
    )
  
  if (do_brut) {
    actor$resources$Brutality$charges <- rb - 1L
    actor$statuses$vex <- list(duration = 1L)
    brut_used <- 1L
  }
  
  # Vex mastery on AoO rapier hit
  if (res$hit &&
      identical(actor$weapon$mastery, "vex")) {
    actor$statuses$vex <- list(duration = 1L)
  }
  
  # Sap mastery on AoO longsword hit
  if (res$hit &&
      identical(actor$weapon$mastery, "sap")) {
    actor$statuses$enemy_sap <- list(pending = TRUE)
  }
  
  # log the AoO attack
  logger$log(
    round, combat,
    actor$name,
    "AoO",
    res$roll,
    res$to_hit,
    res$hit,
    res$crit,
    if (res$hit) res$damage else 0L,
    "Enemy",
    res$notes
  )
  
  list(actor=actor, 
       adv_flag=adv_flag,
       damage   = if (res$hit) res$damage else 0L,
       gs_used = gs_used,
       brut_used = brut_used)
}

#—————————————————————————————————————————————————————————————
# 7) Wrathful Smite Helper Function 
#—————————————————————————————————————————————————————————————
consume_smite_slot <- function(actor) {
  # Pact Slot first
  if (actor$resources$`Pact Slot`$charges > 0L) {
    actor$resources$`Pact Slot`$charges <- actor$resources$`Pact Slot`$charges - 1L
    return(list(actor=actor, slot_level=1L))
  }
  # Free cast
  if (actor$resources$`Smite Free`$charges > 0L) {
    actor$resources$`Smite Free`$charges <- actor$resources$`Smite Free`$charges - 1L
    return(list(actor=actor, slot_level=1L))
  }
  # Cleric Slot1
  if (actor$resources$`Cleric Slot1`$charges > 0L) {
    actor$resources$`Cleric Slot1`$charges <- actor$resources$`Cleric Slot1`$charges - 1L
    return(list(actor=actor, slot_level=1L))
  }
  # Cleric Slot2
  if (actor$resources$`Cleric Slot2`$charges > 0L) {
    actor$resources$`Cleric Slot2`$charges <- actor$resources$`Cleric Slot2`$charges - 1L
    return(list(actor=actor, slot_level=2L))
  }
  # Cleric Slot3
  if (actor$resources$`Cleric Slot3`$charges > 0L) {
    actor$resources$`Cleric Slot3`$charges <- actor$resources$`Cleric Slot3`$charges - 1L
    return(list(actor=actor, slot_level=3L))
  }
  # If no slots available
  return(list(actor=actor, slot_level=0L))
}

#—————————————————————————————————————————————————————————————
# 8) Simulate one adventuring day at a given level (up to 13)
#—————————————————————————————————————————————————————————————
simulate_day_level <- function(level,
                               rounds   = 4L,
                               combats  = 4L,
                               seed     = NULL) {
  if (!is.null(seed)) set_sim_seed(seed)
  
  # set monster based on level 
  monster <- get_monster_row_for_level(level)
  
  # track total swings and how many had advantage
  n_attacks     <- 0L
  n_adv_attacks <- 0L
  
  # track war priest attacks
  war_priest_uses <- 0L
  
  # track wrathful smites 
  smite_uses      <- 0L
  
  # track guided strike uses 
  guided_strike_uses <- 0L
  
  # track Action Surge uses (charges consumed) per day
  action_surge_uses <- 0L
  
  # track Brutality charges used per day
  brutality_uses <- 0L
  
  # track how many times we've cast bless per day 
  bless_uses <- 0L 
  
  # track category-specific damage totals & counts
  att_dmg_total      <- 0  ; att_count      <- 0
  aoo_dmg_total      <- 0  ; aoo_count      <- 0
  wp_dmg_total       <- 0  ; wp_count       <- 0
  ts_dmg_total       <- 0  ; ts_count       <- 0
  smite_dmg_total    <- 0  ; smite_count    <- 0
  
  # track concentration and enemy damage 
  conc_checks <- 0L
  conc_fails  <- 0L
  enemy_dmg_total <- 0
  
  # track second wind and flourish parry/counter uses and damage
  second_wind_uses <- 0L 
  flourish_parry_uses <- 0L 
  flourish_counter_uses <- 0L
  flourish_counter_dmg <- 0
  
  # initialize character and monster AC 
  actor  <- create_war_angel(level)
  logger <- make_logger()
  ac     <- as.integer(monster$ac)
  
  # assign per-combat +0/1/2 magic weapon bonus by level
  if (level <= 4L) {
    magic_bonuses <- rep(0L, combats)
  } else if (level == 5L) {
    magic_bonuses <- sample(c(0L, 1L), combats, replace = TRUE, prob = c(2/3, 1/3))
  } else if (level <= 11L) {
    magic_bonuses <- sample(c(0L, 1L), combats, replace = TRUE, prob = c(1/2, 1/2))
  } else if (level == 12L) {
    # level = 12: always +1, 50% upgrade to +2
    magic_bonuses <- rep(1L, combats) + sample(c(0L, 1L), combats, replace = TRUE, prob = c(1/2, 1/2))
  } else if (level >=13L) {
    # level >= 13: always +1, 75% upgrade to +2
    magic_bonuses <- rep(1L, combats) + sample(c(0L, 1L), combats, replace = TRUE, prob = c(1/4, 3/4))
  }
  
  # ensure integer type
  magic_bonuses <- as.integer(magic_bonuses)
  
  for (c in seq_len(combats)) {
    
    #  pick aoo slot 
    actor$reaction <- TRUE
    actor$aoo_slot <- pick_aoo_slot()
    
    # clear any carried-over vex/sap statuses before this combat starts
    actor$statuses$vex <- NULL
    actor$statuses$enemy_sap <- NULL
    
    # set this combat’s magic weapon bonus
    actor$magic_weapon_bonus <- magic_bonuses[c]
    
    # clear any leftover bless status
    actor$concentration_spell <- NULL

    # go round by round and resolve combat 
    for (r in seq_len(rounds)) {
      
      # short rest at start of combat 2 & start of combat 4
      if ((c == 2L || c == 4L) && r == 1L) {
        actor <- recharge_short(actor)
      }
      
      # set new combat policy
      pol   <- policy_per_level(actor, level, c, r)
      
      # check if we're using flourish parry/counter (lvl-14+)
      actor$use_flourish_parry <- pol$use_flourish_parry
      actor$use_flourish_counter <- pol$use_flourish_counter
      actor$flourish_brutality <- pol$flourish_brutality 
      # set to false if true and we're in a round where we make an aoo 
      if (actor$aoo_slot == (r+0.5) || (identical(actor$aoo_slot, -Inf) && r==1L)){
        actor$use_flourish_parry <- FALSE
        actor$use_flourish_counter <- FALSE
      }
    
      # simulate enemy attack phase and update tracked resources
      pre_conc_checks <- actor$conc_checks
      pre_conc_fails  <- actor$conc_fails
      pre_enemy_dmg   <- actor$enemy_dmg_total
      enemy_res <- enemy_attack_phase(actor, monster, logger, r, c, p_target = 0.50)
      actor <- enemy_res$actor
      conc_checks     <- conc_checks     + (actor$conc_checks - pre_conc_checks)
      conc_fails      <- conc_fails      + (actor$conc_fails  - pre_conc_fails)
      enemy_dmg_total <- enemy_dmg_total + (actor$enemy_dmg_total - pre_enemy_dmg)
      n_attacks     <- n_attacks     + as.integer(unlist(enemy_res$counter_used))
      n_adv_attacks <- n_adv_attacks + as.integer(unlist(enemy_res$adv_flag))
      second_wind_uses <- second_wind_uses + unlist(enemy_res$sw_used)
      flourish_parry_uses <- flourish_parry_uses + as.integer(unlist(enemy_res$parry_used))
      flourish_counter_uses <- flourish_counter_uses + as.integer(unlist(enemy_res$counter_used))
      flourish_counter_dmg <- flourish_counter_dmg + as.numeric(unlist(enemy_res$counter_dmg))
      
      # if slot == –Inf, resolve AoO immediately before round 1
      if (identical(actor$aoo_slot, -Inf) && r == 1L && actor$reaction==TRUE) {
        aoo_res <- resolve_aoo(actor, logger, c, 0L, ac, pol$guided_strike_aoo)
        aoo_count      <- aoo_count + 1L
        aoo_dmg_total  <- aoo_dmg_total + aoo_res$damage
        actor   <- aoo_res$actor
        n_attacks     <- n_attacks     + 1L
        n_adv_attacks <- n_adv_attacks + aoo_res$adv_flag
        guided_strike_uses <- guided_strike_uses + aoo_res$gs_used
        brutality_uses <- brutality_uses + aoo_res$brut_used 
      }
      
      # tick statuses and reset reaction/BA at start of our turn 
      actor <- tick_statuses(actor)
      actor$reaction <- TRUE
      ba_spent <- FALSE 
      
      # Activate shield of faith if that's the policy
      if (pol$use_shield_of_faith && !ba_spent && actor$resources$`Channel Divinity`$charges > 0L) {
        actor$resources$`Channel Divinity`$charges <- actor$resources$`Channel Divinity`$charges - 1L
        actor$statuses$shield_of_faith <- list(duration = rounds - r + 1L)  # or Inf for whole combat
        ba_spent <- TRUE
        logger$log(r, c, actor$name, "Shield of Faith", NA, NA, TRUE, FALSE, 0L, "Self", "+2 AC (CD)")
      }
      
      # Only one bonus action per turn: if using War Priest, you cannot Smite
      if (pol$use_war_priest && pol$use_smite) {pol$use_smite <- FALSE}
      
      # cast bless if specified by the policy and build attack sequence tracker
      if (pol$cast_bless_round1 && is.null(actor$concentration_spell)) {
        bless_uses <- bless_uses + 1L
        actor$concentration_spell <- "bless"
        
        # spend Pact Slot first, then Cleric Slot
        if (actor$resources$`Pact Slot`$charges > 0L) {
          actor$resources$`Pact Slot`$charges <- actor$resources$`Pact Slot`$charges - 1L
        } else if (actor$resources$`Cleric Slot1`$charges > 0L) {
          actor$resources$`Cleric Slot1`$charges <- actor$resources$`Cleric Slot1`$charges - 1L
        }
        
        # if we cast Bless, we skip normal attacks
        n_att_base <- 0L
      } else {
        # normal base attacks
        n_att_base <- if (level >= 10L) 2L else 1L
      }
      
      # handle Action Surge separately
      n_att <- n_att_base
      if (pol$n_action_surge > 0L &&
          actor$resources$`Action Surge`$charges >= pol$n_action_surge) {
        actor$resources$`Action Surge`$charges <-
          actor$resources$`Action Surge`$charges - pol$n_action_surge
        action_surge_uses <- action_surge_uses + pol$n_action_surge
        n_att <- n_att + (if (level >= 10L) 2L else 1L) * pol$n_action_surge
      }
      
      # Build rest of attack sequence tracker
        # 0 = skip (used for overriding entries mid-loop)
        # 1 = base attack 
        # 2 = true-strike attack 
        # 3 = action surge attack 
        # 4 = war priest attack 
      {
      L <- n_att + as.integer(pol$use_war_priest)
      setup_first <- level %in% c(8L, 9L)
      n_war_priest <- as.integer(pol$use_war_priest)
      n_surge_attacks <- if (pol$n_action_surge > 0L) (if (level >= 10L) 2L else 1L) * pol$n_action_surge else 0L
      n_base_attacks  <- n_att_base
      
      want_ts <- pol$use_true_strike
      action_att_block <- c(rep(1L, n_base_attacks), rep(3L, n_surge_attacks))
      if (want_ts && n_base_attacks > 0L) {
        ts_pos <- if (setup_first) length(action_att_block) else 1L
        action_att_block[ts_pos] <- 2L
      }
      
      full_seq <- c(action_att_block, rep(4L, n_war_priest))
      if (length(full_seq) == 0L) {
        attack.seq <- c(0)   # zero vector of length 1
      } else if (setup_first) {
        setup_block <- full_seq[full_seq %in% c(4L, 3L)]
        other_block <- full_seq[full_seq %in% c(2L, 1L)]
        attack.seq  <- c(setup_block, other_block)
      } else {
        attack.seq  <- full_seq
      }
      }
      
      # track bless uptime
      if (!is.null(actor$concentration_spell) &&
          actor$concentration_spell == "bless") {
        actor$bless_rounds_active <- actor$bless_rounds_active + 1L
      }
      
      # Set flag for use of bruatlity this round 
      brutality_used_this_turn <- FALSE
      
      # Set flag for sap applied this round
      actor$flags$sap_applied_this_turn <- FALSE
     
      # Perform attacks + Wrathful smite (potentially)
      for (i in 1:length(attack.seq)) {
        
        # identify the attack type 
        att.type <- attack.seq[i]
        
        # if it's an overridden war priest attack (where we already used our BA to smite) or we already used our 
        # action to cast bless (and aren't using action surge) then then skip this iteration of the loop 
        if (att.type == 0L) next   
        
        # determine if we have vex-granted advantage, and consume it immediately
        if (!is.null(actor$statuses$vex)) {
          adv_flag <- 1L
          actor$statuses$vex <- NULL
        } else {
          adv_flag <- 0L
        }
        
        # roll attack action /true strike attacks and record the swing
        if (att.type %in% c(1,2,3)){
          res <- attack_resolve(actor, ac, adv = adv_flag)
          n_attacks     <- n_attacks + 1L
          n_adv_attacks <- n_adv_attacks + adv_flag
        }
        
        # roll war priest bonus action attacks and record the swing
        if (att.type==4 &&
            !ba_spent && 
            actor$resources$`War Priest`$charges > 0L) {
          # spend the feature
          actor$resources$`War Priest`$charges <- actor$resources$`War Priest`$charges - 1L
          # record that we used War Priest once
          war_priest_uses <- war_priest_uses + 1L
          # update ba_spend 
          ba_spent <- TRUE 
          # roll attack and record the swing 
          res <- attack_resolve(actor, ac, adv = adv_flag)
          n_attacks     <- n_attacks + 1L
          n_adv_attacks <- n_adv_attacks + adv_flag
        }
        
        # stash the raw outcome
        orig_roll   <- res$roll
        orig_to_hit <- res$to_hit
        orig_hit    <- res$hit
        orig_crit   <- res$crit
        actor <- res$attacker
        
        # use Guided Strike if applicable 
        if (!orig_hit &&
            orig_roll  != 1L &&
            pol$use_guided_strike &&
            actor$resources$`Channel Divinity`$charges > 0L &&
            (orig_to_hit + 10L) >= ac) {
          
          # spend the charge and track the usage 
          actor$resources$`Channel Divinity`$charges <-
            actor$resources$`Channel Divinity`$charges - 1L
          guided_strike_uses <- guided_strike_uses + 1L
          
          # bump the to_hit and flip it to a hit
          res$to_hit <- orig_to_hit + 10L
          res$hit    <- TRUE
          
          # re-roll damage exactly once, doubling dice on a nat-20 original
          dice_n <- if (orig_crit) actor$weapon$n_dice * 2L else actor$weapon$n_dice
          res$damage <- roll_dice(dice_n, actor$weapon$die_size) +
            actor$weapon$dmg_mod +
            as.integer(actor$magic_weapon_bonus)
          
          # preserve crit flag (orig_crit) if you want crit effects elsewhere
          res$crit <- orig_crit
        }
        
        # True‐Strike extra damage (1d6, doubled on crit)
        if (res$hit && att.type==2) {
          # choose 2 dice if crit, otherwise 1
          n_ts_dice    <- if (res$crit) 2L else 1L
          extra_true   <- roll_dice(n_ts_dice, sides = 6L)
          res$damage   <- res$damage + extra_true
          ts_count     <- ts_count     + 1L
          ts_dmg_total <- ts_dmg_total + res$damage
        }
        
        # Wrathful Smite extra damage (scales by slot level)
        if (res$hit &&
            !ba_spent && 
            (pol$use_smite || (!pol$use_smite && (pol$prefer_smite_on_crit && res$crit)))
        ) {
          smite_uses <- smite_uses + 1L
          ba_spent <- TRUE
          
          # consume slot with prioritization
          slot_res <- consume_smite_slot(actor)
          actor <- slot_res$actor
          slot_level <- slot_res$slot_level
          
          if (slot_level > 0L) {
            # base dice = slot level d6, doubled on crit
            n_smite_dice <- slot_level * if (res$crit) 2L else 1L
            extra_smite  <- roll_dice(n_smite_dice, 6L)
            res$damage   <- res$damage + extra_smite
            smite_count      <- smite_count + 1L
            smite_dmg_total  <- smite_dmg_total + extra_smite
            res$notes <- paste(res$notes, sprintf("Wrathful Smite L%d +%d", slot_level, extra_smite))
          }
          
          # if we only smite on crit, cancel war priest attack
          if (!pol$use_smite && (pol$prefer_smite_on_crit && res$crit)) {
            attack.seq[attack.seq == 4L] <- 0L
          }
        }
        
        # Brutality::bluff on weapon hit
        if (res$hit &&
            pol$brutality_spend > 0L &&
            actor$resources$Brutality$charges > 0L &&
            !brutality_used_this_turn) {
          actor$resources$Brutality$charges <- actor$resources$Brutality$charges - 1L
          actor$statuses$vex <- list(duration = 1L)
          actor$statuses$brutality_save_adv <- list(duration = 2L)  # current turn and next turn
          pol$brutality_spend <- pol$brutality_spend - 1L
          brutality_uses <- brutality_uses + 1L
          brutality_used_this_turn <- TRUE
        }
        
        # Vex mastery: rapier hit grants vexed status for next attack
        if (res$hit &&
            identical(actor$weapon$mastery, "vex")) {
          actor$statuses$vex <- list(duration = 1L)
        }
        
        # Sap mastery: longsword hit grants sap status for next attack against us
        if (res$hit && identical(actor$weapon$mastery, "sap") && !actor$flags$sap_applied_this_turn) {
          actor$statuses$enemy_sap <- list()    # one-shot flag
          actor$flags$sap_applied_this_turn <- TRUE
        }
        
        # record attack action uses and damage
        if (att.type==1 | att.type==3){
          att_count   <- att_count + 1L
          att_dmg_total <- att_dmg_total + if (res$hit) res$damage else 0L
        }
        
        # record war priest uses and damage
        if (att.type==4){
          wp_count       <- wp_count   + 1L
          wp_dmg_total   <- wp_dmg_total + if (res$hit) res$damage else 0L
        }

        # log the attack
        if (att.type==1 | att.type==3){
        logger$log(r, c, actor$name,
                   "Attack",
                   res$roll,  res$to_hit,
                   res$hit,   res$crit,
                   if (res$hit) res$damage else 0L,
                   "Enemy",   res$notes)
        }
        if (att.type==2){
          logger$log(r, c, actor$name,
                     "TrueStrike Attack",
                     res$roll,  res$to_hit,
                     res$hit,   res$crit,
                     if (res$hit) res$damage else 0L,
                     "Enemy",   res$notes)
        }
        if (att.type==4){
        # log the war priest attack
        logger$log(r, c, actor$name,
                     "WarPriest Attack",
                     res$roll,  res$to_hit,
                     res$hit,   res$crit,
                     if (res$hit) res$damage else 0L,
                     "Enemy",   res$notes)
        }
      }
      
      # Attack of Opportunity in between rounds 
      if (actor$aoo_slot == (r+0.5) && actor$reaction==TRUE) {
        aoo_res <- resolve_aoo(actor, logger, c, r, ac, pol$guided_strike_aoo)
        aoo_count      <- aoo_count + 1L
        aoo_dmg_total  <- aoo_dmg_total + aoo_res$damage
        actor   <- aoo_res$actor
        n_attacks     <- n_attacks     + 1L
        n_adv_attacks <- n_adv_attacks + aoo_res$adv_flag
        guided_strike_uses <- guided_strike_uses + aoo_res$gs_used
        brutality_uses <- brutality_uses + aoo_res$brut_used 
      }
      
      # final AoO after round 4
      if (identical(actor$aoo_slot, Inf) && r == 4L && actor$reaction==TRUE) {
        aoo_res <- resolve_aoo(actor, logger, c, Inf, ac, pol$guided_strike_aoo)
        aoo_count      <- aoo_count + 1L
        aoo_dmg_total  <- aoo_dmg_total + aoo_res$damage
        actor   <- aoo_res$actor
        n_attacks     <- n_attacks     + 1L
        n_adv_attacks <- n_adv_attacks + aoo_res$adv_flag
        guided_strike_uses <- guided_strike_uses + aoo_res$gs_used
        brutality_uses <- brutality_uses + aoo_res$brut_used 
      }
    }
  }
  
  # long rest at end of day
  actor <- recharge_long(actor)
  
  # summarize and report tracked resources 
  lg <- logger$get()
  attack_rows <- lg$action %in% c("Attack", "TrueStrike Attack", "WarPriest Attack", "AoO", "Flourish Counter")
  lg_att <- if (nrow(lg) > 0) lg[attack_rows, ] else data.table()
  total_attacks <- if (nrow(lg_att) > 0) nrow(lg_att) else 0L
  total_misses <- if (nrow(lg_att) > 0) sum(!lg_att$hit) else 0L
  bless_share  <- actor$bless_rounds_active / (rounds*combats)
  data.table(
    level            = level,
    dpr              = sum(lg$damage) / (rounds * combats),
    hit_rate         = if (total_attacks > 0) sum(lg_att$hit)  / total_attacks else NA_real_,
    crit_rate        = if (total_attacks > 0) sum(lg_att$crit) / total_attacks else NA_real_,
    adv_rate         = if (total_attacks > 0) n_adv_attacks    / total_attacks else NA_real_,
    war_priest       = war_priest_uses,
    smite            = smite_uses,
    guided_strike    = guided_strike_uses,
    total_attacks    = total_attacks,
    total_misses     = total_misses,
    action_surges    = action_surge_uses,
    brutalities      = brutality_uses,
    avg_att_dmg      = if (att_count>0)      att_dmg_total      / att_count      else NA_real_,
    avg_aoo_dmg      = if (aoo_count>0)      aoo_dmg_total      / aoo_count      else NA_real_,
    avg_wp_dmg       = if (wp_count>0)       wp_dmg_total       / wp_count       else NA_real_,
    avg_true_strike  = if (ts_count>0)       ts_dmg_total       / ts_count       else NA_real_,
    avg_smite        = if (smite_count>0)    smite_dmg_total    / smite_count    else NA_real_,
    enemy_damage     = enemy_dmg_total,
    conc_checks      = conc_checks,
    conc_fail_rate   = if (conc_checks > 0) conc_fails / conc_checks else NA_real_,
    bless_active     = bless_share,
    bless_uses       = bless_uses, 
    second_wind_uses = second_wind_uses,
    flourish_parry_uses = flourish_parry_uses, 
    flourish_counter_uses = flourish_counter_uses,
    flourish_counter_dmg = if (flourish_counter_uses>0) flourish_counter_dmg / flourish_counter_uses  else NA_real_
  )
}


#—————————————————————————————————————————————————————————————
# 9) Batch runner for levels 1–13
#—————————————————————————————————————————————————————————————
batch_simulate_level <- function(level,
                                 n    = 1000L,
                                 seed = 42L) {
  set_sim_seed(seed)
  sims <- replicate(
    n,
    simulate_day_level(
      level,
      seed = sample.int(1e8, 1L)
    ),
    simplify = FALSE
  )
  
  out <- rbindlist(lapply(sims, function(x) 
    data.table(
      level           = x$level,
      dpr             = x$dpr,
      total_attacks   = x$total_attacks,
      total_misses    = x$total_misses,
      hit             = x$hit_rate,
      crit            = x$crit_rate,
      adv             = x$adv_rate,
      war_priest      = x$war_priest,
      guided_strike   = x$guided_strike,
      smite           = x$smite,
      action_surges   = x$action_surges,
      brutalities     = x$brutalities,
      avg_att_dmg     = x$avg_att_dmg,
      avg_aoo_dmg     = x$avg_aoo_dmg,
      avg_wp_dmg      = x$avg_wp_dmg,
      avg_true_strike = x$avg_true_strike,
      avg_smite       = x$avg_smite, 
      enemy_dmg       = x$enemy_damage,
      conc_checks     = x$conc_checks, 
      conc_fail_rate  = x$conc_fail_rate,
      bless_active    = x$bless_active,
      bless_uses      = x$bless_uses,
      second_winds    = x$second_wind_uses,
      fl_parries      = x$flourish_parry_uses,
      fl_counters     = x$flourish_counter_uses,
      fl_counter_dmg  = x$flourish_counter_dmg
    )
  ))
  
  out[, .(
    dpr              = mean(dpr),
    total_attacks    = mean(total_attacks),
    total_misses     = mean(total_misses),
    hit              = mean(hit),
    crit             = mean(crit),
    adv              = mean(adv),
    war_priest       = mean(war_priest),
    guided_strike    = mean(guided_strike),
    smite            = mean(smite),
    action_surges    = mean(action_surges),
    brutalities      = mean(brutalities), 
    avg_att_dmg      = mean(avg_att_dmg),
    avg_aoo_dmg      = mean(avg_aoo_dmg),
    avg_wp_dmg       = mean(avg_wp_dmg),
    avg_true_strike  = mean(avg_true_strike),
    avg_smite        = mean(avg_smite),
    enemy_dmg        = mean(enemy_dmg),
    conc_checks      = mean(conc_checks),
    conc_fail_rate   = mean(conc_fail_rate,na.rm=T),
    bless_active     = mean(bless_active),
    bless_uses       = mean(bless_uses),
    second_winds     = mean(second_winds),
    fl_parries       = mean(fl_parries),
    fl_counters      = mean(fl_counters),
    fl_counter_dmg   = mean(fl_counter_dmg,na.rm=T)
  ), by = level]
}

#—————————————————————————————————————————————————————————————
# End of war_angel_sim.R
#—————————————————————————————————————————————————————————————