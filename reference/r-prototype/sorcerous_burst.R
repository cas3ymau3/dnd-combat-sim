# Clear workspace/console and load packages
{
  rm(list=ls()) # clear workspace  
  cat("\014") # clear console
  pkgs <- c("tidyverse","tidyr","dplyr","purrr", # define requisite packages
            "here","stringr","Hmisc","sf","sp",
            "lubridate","data.table","fixest")
  lapply(pkgs, require, character.only = TRUE) # load requisite packages
  rm(pkgs)
  gc()
}

# Sorcerous burst damage 
  # flames of phlegethos = reroll 1's on fire dmg 
  # elemental adept (fire) = treat any 1 as a 2 
  # spell sniper 
  # searing smite 

# Create base function for calculating sorcerous burst (sb) damage
sb <- function(lvl,cha.mod,empowered,thresh,flames,adept){
  if (lvl<5){ndie <- 1}
  if (lvl>=5 & lvl<11){ndie <- 2}
  if (lvl>=11 & lvl<17){ndie <- 3}
  if (lvl>=17){ndie <- 4}
  rerolls <- cha.mod
  nempower <- cha.mod
  DMG <- 0
  for (i in 1:ndie){
    roll <- sample(1:8,1)
    if (flames==1 & roll==1){roll <- sample(1:8,1)}
    if (empowered==1 & nempower>0 & roll<=thresh){
      roll <- sample(1:8,1)
      nempower <- nempower-1
    }
    if (adept==1 & roll==1){roll <- 2}
    dmg <- roll 
    add.roll <- roll 
    while (rerolls>0 & add.roll==8){
      add.roll <- sample(1:8,1)
      if (flames==1 & add.roll==1){add.roll <- sample(1:8,1)}
      if (empowered==1 & nempower>0 & add.roll<=thresh){
        add.roll <- sample(1:8,1)
        nempower <- nempower-1
      }
      if (adept==1 & add.roll==1){add.roll <- 2}
      dmg <- dmg + add.roll
      rerolls <- rerolls-1
    }
    DMG <- DMG + dmg
    rm(i,roll,dmg,add.roll)
  }
  if (lvl>=3 & lvl<14){
    radiant.fire <- sample(1:6,1)
    if (radiant.fire==1 & adept==1){radiant.fire==2}
    DMG <- DMG + radiant.fire
  }
  if (lvl>=14){
    radiant.fire <- c(sample(1:6,1),sample(1:6,1),sample(1:6,1))
    if(adept==1){radiant.fire[which(radiant.fire==1)] <- 2}
    DMG <- DMG + sum(radiant.fire)
  }
  return(DMG)
}

# Now factor in chance to hit/crit, enemy AC, etc. 
# Create dataframe to store results 
results.df <- data.frame("lvl"=1:20,
                         "PB"=c(rep(2,4),rep(3,4),rep(4,4),rep(5,4),rep(6,4)),
                         "cha.mod"=c(rep(3,3),rep(4,4),rep(5,13)),
                         "flames"=c(rep(0,3),rep(1,17)),
                         "adept"=c(rep(0,11),rep(1,9)),
                         "enemy.AC"=c(rep(13,3),14,rep(15,3),rep(16,2),rep(17,3),rep(18,4),rep(19,2),rep(20,2)),
                         "EDSB"=NA)

# Create function to incorporate chance to hit
sb2 <- function(lvl,empowered,thresh,innate,wand,bless,potent){
  pb <- results.df$PB[which(results.df$lvl==lvl)]
  ac <- results.df$enemy.AC[which(results.df$lvl==lvl)]
  cha.mod <- results.df$cha.mod[which(results.df$lvl==lvl)]
  flames <- results.df$flames[which(results.df$lvl==lvl)]
  adept <- results.df$adept[which(results.df$lvl==lvl)]
  attack.roll <- sample(1:20,1)
  if (innate==1){attack.roll <- max(attack.roll,sample(1:20,1))}
  crit <- as.numeric(attack.roll==20)
  if (wand==1){attack.roll <- attack.roll+1}
  if (bless==1){attack.roll <- attack.roll + sample(1:4,1)}
  attack.roll <- attack.roll + pb + cha.mod
  damage <- as.numeric(attack.roll>=ac)*sb(lvl,cha.mod,empowered,thresh,flames,adept) + 
            0.5*as.numeric(attack.roll<ac)*sb(lvl,cha.mod,empowered,thresh,flames,adept)*as.numeric(potent==1)
  if (crit==1){damage <- damage*2}
  return(damage)
}

# Loop over levels and compute expected sorcerous burst damage 
niter <- 10000
for (r in 1:nrow(results.df)){
  lvl <- results.df$lvl[r]
  results.df$EDSB[r] <- mean(as.vector(unlist(lapply(as.list(1:niter),function(x) sb2(lvl,
                                                                                      empowered=1,
                                                                                      thresh=5,
                                                                                      innate=1,
                                                                                      wand=1,
                                                                                      bless=1,
                                                                                      potent=1)))))
  rm(lvl,r)
}




