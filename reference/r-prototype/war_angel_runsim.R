rm(list=ls())
cat("\014")
setwd("C:/Users/cmaue/OneDrive/Desktop/desktemp/theory_craft/dnd_chars/2024_PHB/favorites/38_the_war_angel")
source("war_angel_phase1.R")
source("war_angel_sim.R")

# Load monster table
library(readxl)
monster_df <- read_xlsx("monster_ac_and_saves_by_level.xlsx")
set_monster_table(monster_df)

# Run level simulation
res <- batch_simulate_level(level=15, n=4000, seed=123)
print(res)


# lvl-01: 8.32  (rapier)
# lvl-02: 7.39  (pact of the blade, longsword)
# lvl-03: 7.39  
# lvl-04: 6.81  (monster AC increases)
# TIER 01 AVG: 7.48 = C-level
# lvl-05: 16.73 (true-strike + war priest + guided strike)
# lvl-06: 21.03 (shadow touched + wrathful smite)
# lvl-07: 21.26 (action surge, monster ac increases)
# lvl-08: 23.36 (brutality)
# lvl-09: 27.59 (ASI: CHA=20)
# lvl-10: 35.32 (extra attack)
# TIER-02 AVG: 24.22 = C-level
# lvl-11: 33.70 (monster AC increases)
# lvl-12: 38.11 (+2 magic weapon)
# lvl-13: 34.68 (bless + SoF)
# lvl-14: 37.95 (flourish parry w/ bleed)
# lvl-15: 36.59 (monster AC increases, w/bluff = 36.08)
# lvl-16: XX.XX (tactical master + indomitable)




# TROUBLE SHOOTING 
# Run a single day simulation at level 14
actor  <- create_war_angel(14)

# simulate just one day with 1 combat, 1 round
debug_res <- simulate_day_level(level = 14, rounds = 4, combats = 4, seed = 41)

# Look at the raw log
print(debug_res)




