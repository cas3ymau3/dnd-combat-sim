# war_angel_phase1.R
# Core simulation engine with general rules/updates

library(data.table)

# RNG helper
set_sim_seed <- function(seed) if (!is.null(seed)) set.seed(seed)

# Dice utilities
roll_dice <- function(n = 1L, sides = 6L) {
  sum(sample.int(as.integer(sides), as.integer(n), replace = TRUE))
}
roll_d20 <- function(adv = 0L) {
  if (adv == 1L) return(max(sample.int(20L, 2L, replace = TRUE)))
  if (adv == -1L) return(min(sample.int(20L, 2L, replace = TRUE)))
  sample.int(20L, 1L)
}
roll_save <- function(base_mod = 0L, adv = 0L, bless_active = FALSE) {
  d20 <- roll_d20(adv)
  bonus <- base_mod
  if (bless_active) bonus <- bonus + roll_dice(1L, 4L)  # +1d4
  list(total = d20 + bonus, roll = d20, bonus_added = bonus)
}

# AoO timing helper (Inf=after round 4)
pick_aoo_slot <- function() sample(c(-Inf, 1.5, 2.5, 3.5, Inf), 1)

# Constructors
make_weapon <- function(name, n_dice, die_size, dmg_mod = 0L, mastery = NULL, attack_stat = NULL) {
  list(name = name,
       n_dice = as.integer(n_dice),
       die_size = as.integer(die_size),
       dmg_mod = as.integer(dmg_mod),
       mastery = mastery,
       attack_stat = attack_stat)
}

make_resource <- function(name, charges, rec_short = FALSE, rec_long = TRUE,
                          dice = list(n = 1L, sides = 6L),
                          extra_on_crit = list(n = 1L, sides = 6L)) {
  list(name = name,
       charges = as.integer(charges),
       max = as.integer(charges),
       recharge = list(short = rec_short, long = rec_long),
       dice = dice,
       extra_on_crit = extra_on_crit)
}

make_actor <- function(name, level, hp, ac, prof, ability_mods,
                       weapon, resources = list(), statuses = list(),
                       save_mods = NULL) {
  if (is.null(save_mods)) {
    save_mods <- list(
      str = ability_mods$str,
      dex = ability_mods$dex,
      con = ability_mods$con,
      int = ability_mods$int,
      wis = ability_mods$wis,
      cha = ability_mods$cha
    )
  }
  
  list(
    name = name,
    level = level,
    hp = hp, max_hp = hp,
    ac = ac,
    prof = prof,
    ability_mods = ability_mods,
    save_mods = save_mods,
    weapon = weapon,
    resources = resources,
    statuses = statuses,
    reaction = TRUE,
    aoo_slot = pick_aoo_slot(),
    magic_weapon_bonus = 0L,
    concentration_spell = NULL,
    conc_checks = 0L,
    conc_fails  = 0L,
    enemy_dmg_total = 0L,
    flags = list(sap_applied_this_turn = FALSE),
    bless_rounds_active = 0L,
    use_flourish_parry = FALSE, 
    use_flourish_counter = FALSE
  )
}

# Status management
tick_statuses <- function(actor) {
  to_rm <- c()
  for (k in names(actor$statuses)) {
    if (k %in% c("vex", "enemy_sap")) next  # vex/sap are consumed by attacks (ours/enemies'), not by time
    st <- actor$statuses[[k]]
    if (!is.null(st$duration)) {
      st$duration <- st$duration - 1L
      if (st$duration <= 0L) to_rm <- c(to_rm, k) else actor$statuses[[k]] <- st
    }
  }
  if (length(to_rm)) actor$statuses[to_rm] <- NULL
  actor
}

# Logging
make_logger <- function() {
  ev <- list()
  log <- function(round, combat, actor, action, roll, to_hit, hit, crit, dmg, target, notes) {
    ev[[length(ev)+1]] <<- data.table(
      combat, round, actor, action,
      roll = as.integer(roll),
      to_hit = as.integer(to_hit),
      hit = as.logical(hit),
      crit = as.logical(crit),
      damage = as.numeric(dmg),
      target = as.character(target),
      notes = as.character(notes)
    )
  }
  get <- function() if (length(ev)==0) data.table() else rbindlist(ev)
  list(log=log, get=get)
}

# Core attack resolve (with Magic Weapon bonus)
attack_resolve <- function(att,
                           target_ac,
                           adv       = 0L) {
  roll   <- roll_d20(adv)
  nat1   <- (roll == 1L)
  nat20  <- (roll == 20L)
  stat <- att$weapon$attack_stat
  
  # include magic‐weapon bonus on attack
  atk_bonus <- att$prof +
    att$ability_mods[[stat]] +
    as.integer(att$magic_weapon_bonus)
  
  # bless to-hit bonus if concentrating on bless
  bless_bonus <- if (!is.null(att$concentration_spell) && att$concentration_spell == "bless") roll_dice(1L, 4L) else 0L
  
  # compute whether or not we hit
  to_hit <- roll + atk_bonus + bless_bonus
  hit  <- !nat1 && (nat20 || to_hit >= target_ac)
  crit <- nat20
  
  dmg   <- 0L
  notes <- character(0)
  if (bless_bonus > 0) notes <- c(notes, paste0("Bless +", bless_bonus))
  
  if (hit) {
    # weapon dice (doubled dice on crit)
    dice_n <- if (crit) att$weapon$n_dice * 2L else att$weapon$n_dice
    dmg    <- dmg +
      roll_dice(dice_n, att$weapon$die_size) +
      att$weapon$dmg_mod +
      as.integer(att$magic_weapon_bonus)
  }
  
  list(
    hit      = hit,
    crit     = crit,
    damage   = dmg,
    roll     = roll,
    to_hit   = to_hit,
    attacker = att,
    notes = paste(notes, collapse="; ")
  )
}
