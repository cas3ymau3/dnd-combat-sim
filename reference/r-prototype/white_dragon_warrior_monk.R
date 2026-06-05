set.seed(1)

# --- Parameters ---
AC <- 16
to_hit_base <- 7
dex_mod <- 4

# --- Dice ---
roll_d6 <- function(n) sample(1:6, n, replace = TRUE)
roll_d20 <- function(n = 1) sample(1:20, n, replace = TRUE)
is_crit <- function(d20) d20 == 20

# --- Attack roll ---
resolve_attack <- function(adv = FALSE, dis = FALSE, to_hit = to_hit_base, AC = AC,
                           allow_insp = FALSE, have_insp = FALSE, reroll_lowest = FALSE) {
  stopifnot(!(adv && dis))
  d20s <- if (adv) roll_d20(2) else if (dis) roll_d20(2) else roll_d20(1)
  attack_d20 <- if (adv) max(d20s) else if (dis) min(d20s) else d20s[1]
  crit <- is_crit(attack_d20)
  hit <- (attack_d20 + to_hit) >= AC || crit
  used_insp <- FALSE
  if (!hit && allow_insp && have_insp && adv && reroll_lowest) {
    low_idx <- which.min(d20s)
    d20s[low_idx] <- roll_d20(1)
    attack_d20 <- max(d20s)
    crit <- is_crit(attack_d20)
    hit <- (attack_d20 + to_hit) >= AC || crit
    used_insp <- TRUE
  }
  list(hit = hit, crit = crit, used_insp = used_insp)
}

# --- Damage ---
dagger_main_damage <- function(crit = FALSE, magic_bonus = 0) {
  (if (crit) sum(roll_d6(2)) else sum(roll_d6(1))) + dex_mod + magic_bonus
}
dagger_offhand_damage <- function(crit = FALSE) {
  if (crit) sum(roll_d6(2)) else sum(roll_d6(1))
}
unarmed_damage <- function(crit = FALSE) {
  (if (crit) sum(roll_d6(2)) else sum(roll_d6(1))) + dex_mod
}

# --- Saves for grapple ---
enemy_fails_grapple_save <- function(dc = 15, save_bonus = 4) {
  (roll_d20(1) + save_bonus) < dc
}
enemy_breaks_grapple <- function(dc = 15, save_bonus = 4) {
  (roll_d20(1) + save_bonus) >= dc
}

# --- One round ---
resolve_round <- function(state) {
  dmg <- 0
  trapped_in_fog_this_round <- FALSE
  
  do_dagger_main <- function(advantage, is_oa = FALSE) {
    mw <- if (state$magic_weapon) 1 else 0
    res <- resolve_attack(
      adv = advantage, dis = FALSE, to_hit = to_hit_base + mw, AC = AC,
      allow_insp = is_oa, have_insp = state$heroic_insp_avail, reroll_lowest = TRUE
    )
    if (is_oa && res$used_insp) state$heroic_insp_avail <<- FALSE
    if (res$hit) dagger_main_damage(crit = res$crit, magic_bonus = mw) else 0
  }
  
  do_dagger_offhand <- function(advantage, is_oa = FALSE) {
    res <- resolve_attack(
      adv = advantage, dis = FALSE, to_hit = to_hit_base, AC = AC,
      allow_insp = is_oa, have_insp = state$heroic_insp_avail, reroll_lowest = TRUE
    )
    if (is_oa && res$used_insp) state$heroic_insp_avail <<- FALSE
    if (res$hit) dagger_offhand_damage(crit = res$crit) else 0
  }
  
  do_unarmed_damage_attack <- function(advantage) {
    res <- resolve_attack(adv = advantage, dis = FALSE, to_hit = to_hit_base, AC = AC)
    if (res$hit) unarmed_damage(crit = res$crit) else 0
  }
  
  # --- NEW: Grapple attempt without attack roll ---
  attempt_grapple <- function() {
    enemy_fails_grapple_save(dc = 15, save_bonus = 4)
  }
  
  advantage_now <- state$in_fog
  
  # --- Our turn ---
  if (state$round_idx == 1 && state$in_fog_original) {
    if (state$do_fob) {
      g1 <- attempt_grapple()
      if (g1) {
        state$grappled <- TRUE
        dmg <- dmg + do_unarmed_damage_attack(advantage_now)
      } else {
        g2 <- attempt_grapple()
        if (g2) state$grappled <- TRUE
      }
    }
  } else {
    dmg <- dmg + do_dagger_main(advantage_now, is_oa = FALSE)
    dmg <- dmg + do_dagger_offhand(advantage_now, is_oa = FALSE)
    if (state$do_fob) {
      if (state$grappled) {
        dmg <- dmg + do_unarmed_damage_attack(advantage_now)
        dmg <- dmg + do_unarmed_damage_attack(advantage_now)
      } else {
        g1 <- attempt_grapple()
        if (g1) {
          state$grappled <- TRUE
          dmg <- dmg + do_unarmed_damage_attack(advantage_now)
        } else {
          g2 <- attempt_grapple()
          if (g2) state$grappled <- TRUE
        }
      }
    }
  }
  
  # --- Enemy turn ---
  if (state$grappled) {
    if (enemy_breaks_grapple(dc = 15, save_bonus = 4)) {
      state$grappled <- FALSE
      if (state$in_fog) {
        oa_dmg <- do_dagger_main(advantage = TRUE, is_oa = TRUE)
        dmg <- dmg + oa_dmg
        if (oa_dmg > 0) trapped_in_fog_this_round <- TRUE else state$in_fog <- FALSE
      } else {
        if (runif(1) < 1/3) {
          oa_dmg <- do_dagger_main(advantage = FALSE, is_oa = TRUE)
          dmg <- dmg + oa_dmg
        }
      }
    } else {
      trapped_in_fog_this_round <- state$in_fog
    }
  } else {
    if (state$in_fog) {
      oa_dmg <- do_dagger_main(advantage = TRUE, is_oa = TRUE)
      dmg <- dmg + oa_dmg
      if (oa_dmg > 0) trapped_in_fog_this_round <- TRUE else state$in_fog <- FALSE
    } else {
      if (runif(1) < 1/3) {
        oa_dmg <- do_dagger_main(advantage = FALSE, is_oa = TRUE)
        dmg <- dmg + oa_dmg
      }
    }
  }
  
  if (!state$in_fog_original) trapped_in_fog_this_round <- FALSE
  
  list(state = state, dmg = dmg, trapped = trapped_in_fog_this_round)
}

# --- One combat ---
simulate_combat <- function(in_fog, magic_weapon, use_fob, heroic_insp_avail) {
  state <- list(
    in_fog = in_fog,
    in_fog_original = in_fog,
    magic_weapon = magic_weapon,
    heroic_insp_avail = heroic_insp_avail,
    grappled = FALSE,
    do_fob = use_fob,
    round_idx = NA
  )
  per_round_dmg <- numeric(4)
  trapped_flags <- logical(4)
  for (r in 1:4) {
    state$round_idx <- r
    res <- resolve_round(state)
    state <- res$state
    per_round_dmg[r] <- res$dmg
    trapped_flags[r] <- res$trapped
  }
  list(total_dmg = sum(per_round_dmg),
       per_round_dmg = per_round_dmg,
       trapped_flags = trapped_flags,
       end_state = state)
}

# --- One day (4 combats) ---
simulate_day <- function() {
  heroic_insp <- TRUE
  # Combats 1–3: Fog; Magic Weapon in 1–2; FoB on
  c1 <- simulate_combat(TRUE,  TRUE,  TRUE,  heroic_insp); heroic_insp <- c1$end_state$heroic_insp_avail
  c2 <- simulate_combat(TRUE,  TRUE,  TRUE,  heroic_insp); heroic_insp <- c2$end_state$heroic_insp_avail
  c3 <- simulate_combat(TRUE,  FALSE, TRUE,  heroic_insp); heroic_insp <- c3$end_state$heroic_insp_avail
  # Combat 4: No Fog, no Magic Weapon, no FoB
  c4 <- simulate_combat(FALSE, FALSE, FALSE, heroic_insp)
  list(combats = list(c1 = c1, c2 = c2, c3 = c3, c4 = c4))
}

# --- Many days + summary ---
simulate_many_days <- function(n_days = 1000) {
  total_damage <- 0
  total_rounds <- 0
  trapped_rounds <- 0
  trap_possible_rounds <- 0
  for (i in 1:n_days) {
    day <- simulate_day()
    for (cname in names(day$combats)) {
      cmb <- day$combats[[cname]]
      total_damage <- total_damage + cmb$total_dmg
      total_rounds <- total_rounds + length(cmb$per_round_dmg)
      if (cname %in% c("c1","c2","c3")) {
        trapped_rounds <- trapped_rounds + sum(cmb$trapped_flags)
        trap_possible_rounds <- trap_possible_rounds + length(cmb$trapped_flags)
      }
    }
  }
  list(
    average_damage_per_round = total_damage / total_rounds,
    average_trapped_share = trapped_rounds / trap_possible_rounds
  )
}

# --- Run and print ---
results <- simulate_many_days(1000)
cat("Average DPR across all combats:", round(results$average_damage_per_round, 3), "\n") # 15.97
cat("Average share of Fog Cloud rounds enemy trapped:", round(results$average_trapped_share, 3), "\n") # 0.882