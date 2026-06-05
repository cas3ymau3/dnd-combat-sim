

################################################################################################################

# EDITS 
# 4 combats per day, 4 rounds per combat 
# Determine fixed share of spell slots used on combat spells (e.g., 50%)
# Include damage from combat inspiration as part of bard's damage (100% usage rate, 5% chance of crit)


# Clear workspace/console and load packages
{
  rm(list=ls()) # clear workspace  
  cat("\014") # clear console
  pkgs <- c("tidyverse","tidyr","dplyr","plyr","purrr", # define requisite packages
            "here","stringr","Hmisc","data.table")
  lapply(pkgs, require, character.only = TRUE) # load requisite packages
  rm(pkgs)
  gc()
}

# Define fixed global parameters 
{
padv.ext <- 0.25  # external probability of advantage 
pdis.ext <- 0.1   # external probability of disadvantage 
pconc <- 0.75     # fixed probability of maintaining concentration on a spell 
emb.pconc <- 0.15 # bonus probability of maintaining concentration if you have eldritch mind 
phbc <- 0.9       # fixed probability that target of attack has cursed condition on turns after using hexblade's curse
pvex <- 0.85      # fixed probability that you target the same enemy to which you applied vex on the previous turn
global.params <- list(padv.ext,
                      pdis.ext,
                      pconc,
                      emb.pconc,
                      phbc,
                      pvex)
names(global.params) <- c("padv.ext",
                          "pdis.ext",
                          "pconc",
                          "emb.pconc",
                          "phbc",
                          "pvex")
rm(padv.ext,pdis.ext,pconc,emb.pconc,phbc,pvex)
}

# Define state variable vector 
{
names <- c("advantage", # advantage 0/1
           "disadvantage", # disadvantage 0/1
           "ext.adv", # external source of advantage (e.g., from ally/environment); updates each turn 
           "ext.dadv", # external source of disadvantage (e.g., from enemy/environment); updates each turn 
           "luck.pts", # number of luck points we have available to use 
           "spells", # what spell(s) are active/being concentrated on
           "concentration", # are we maintaining concentration on a spell 
           "vexed", # is the enemy affected by the vex weapon mastery 
           "hbcursed", # is the enemy affected by hexblade's curse 
           "controlled", # controlled status conveyed by: thl, ff, hp, bd, gi, fom, hm, yrp
           "ncontrolled", # no. of controlled enemies (for upcast spells)
           "witch.bolt0", # initial cast of witch bolt, feed into single attack function
           "witch.bolt1", # concentrating on witch bolt, get BA 1d12
           "auto.crit", # auto-crit status conveyed by hold person / hold monster
           "cursed0", # damage rider effect conveyed by upcast bestow curse spell (no concentration required)
           "cursed1") # damage rider effect conveyed by normal bestow curse spell (concentration required)
state <- as.data.frame(matrix(rep(NA,length(names)),1,length(names)))
colnames(state) <- names
rm(names)  
}

# Create data on average monster stats by level (uncomment to reprocess raw data)
{
  # monster.data <- read.csv("C:/Users/cmaue/OneDrive/Desktop/desktemp/theory_craft/dnd_chars/2024_PHB/in_progress/monster_ac_and_saves.csv",
  #                          header = T)
  # # for each level 1-20, select a set of random samples from the monster table where the CR drawn from a normal distribution centered 
  # # on the character level with a standard deviation of 1.5 levels, then average all the monster stats from across the sample 
  # # have to rename CR-1/8 thru CR-1/2 to do this 
  # monster.data$cr[which(monster.data$cr==0.13)] <- -3
  # monster.data$cr[which(monster.data$cr==0.25)] <- -2 
  # monster.data$cr[which(monster.data$cr==0.5)] <- -1
  # avg.monster <- function(lvl, monster.data, nsamp, stdev){
  #   crs <- plyr::round_any(as.vector(unlist(rnorm(nsamp,mean=lvl,sd=stdev))),1)
  #   crs[which(crs < -3)] <- -3
  #   crs[which(crs > 30)] <- 30
  #   crs <- sort(crs)
  #   df <- as.data.frame(matrix(rep(NA, length(crs)*(ncol(monster.data)-1)),
  #                              nrow = length(crs),
  #                              ncol = ncol(monster.data)-1))
  #   colnames(df) <- c("cr",colnames(monster.data)[3:ncol(monster.data)])
  #   df$cr <- crs 
  #   for (i in 1:nrow(df)){
  #     row <- which(monster.data$cr==df$cr[i])
  #     df[i,2:ncol(df)] <- monster.data[row,3:ncol(monster.data)]
  #     rm(i)
  #   }
  #   avg <- as.data.frame(t(as.matrix(apply(df,2,function(x) plyr::round_any(mean(x),1)))))
  #   colnames(avg) <- colnames(df)
  #   rm(df,crs)
  #   gc()
  #   return(avg)
  # }
  # nsamp <- 10000
  # stdev <- 1
  # monster.table <- as.data.frame(do.call("rbind",lapply(as.list(1:20),function(x) avg.monster(x,monster.data,nsamp,stdev))))
  # # manually modify this a bit just so things are monotonic by level 
  # monster.table$ac[17] <- 18
  # monster.table$ac[19] <- 19
  # write.csv(monster.table,
  #           file="C:/Users/cmaue/OneDrive/Desktop/desktemp/theory_craft/dnd_chars/2024_PHB/in_progress/monster_ac_and_saves_by_level.csv")
}

# Create table of parameters that vary by character level. 
{
monster.table <- read.csv("C:/Users/cmaue/OneDrive/Desktop/desktemp/theory_craft/dnd_chars/2024_PHB/in_progress/monster_ac_and_saves_by_level.csv")
lvl.params <- data.frame("lvl"=1:20,
                         "enemy.ac"=monster.table$ac,
                         "enemy.save.str" = monster.table$str.save.mod,
                         "enemy.save.dex" = monster.table$dex.save.mod,
                         "enemy.save.con" = monster.table$con.save.mod,
                         "enemy.save.int" = monster.table$int.save.mod,
                         "enemy.save.wis" = monster.table$wis.save.mod,
                         "enemy.save.cha" = monster.table$cha.save.mod,
                         "pb"=c(rep(2,4),rep(3,4),rep(4,4),rep(5,4),rep(6,4)),
                         "luck.pts"=c(rep(2,4),rep(3,4),rep(4,4),rep(5,4),rep(6,4)),
                         "attack.mod"=c(rep(3,4),rep(4,8),rep(5,8)),
                         "weapon"=c(rep("light.crossbow",3),rep("pistol",16),"musket"),
                         "true.strike"=c(rep(0,4),rep(1,6),rep(2,6),rep(3,4)),
                         "thorn.whip"=c(rep(1,4),rep(2,6),rep(3,6),rep(4,4)),
                         "sneak.att"=c(0,rep(1,17),2,2),
                         "svg.att"=c(rep(0,2),rep(1,18)),
                         "pierce"=c(rep(0,8),rep(1,12)),
                         "charge"=c(rep(0,16),rep(1,4)),
                         "eld.mind"=c(0,0,1,1,rep(0,16)),
                         "agonize"=c(rep(0,4),rep(1,16)),
                         stringsAsFactors = F)
}

# Create `cast.spell` function
cast.spell <- function(lvl,spell,spell.lvl){
    
    # Get spell DC from lvl.params 
    row <- which(lvl.params$lvl==lvl)
    dc <- 8 + lvl.params$pb[row] + lvl.params$attack.mod[row]
    
    # Set base state for enemy saving throw 
    save <- 1 
    saving.throw <- 99
    
    # Witch bolt
    if (spell=="wb"){
      state$spells <- as.vector(c(na.omit(state$spells),"wb"))
      state$witch.bolt0 <- 1 
      state$witch.bolt1 <- 1 
      state$concentration <- 1
    }
  
    # Tasha's Hideous Laughter (WIS)
    if (spell=="thl"){
        # spell targets # of enemies equal to spell level 
        i <- 1 
        while (i <= spell.lvl){
          saving.throw <- sample(1,1:20) + lvl.params$enemy.save.wis[row]
          if (saving.throw < dc){
            state$spells <- as.vector(c(na.omit(state$spells),"thl"))
            state$concentration <- 1
            state$controlled <- 1
            state$ncontrolled <- state$ncontrolled + 1
          }
          i <- i +1
        }
        rm(i,saving.throw)
    }
    
    # Faerie Fire (DEX)
    if (spell=="ff"){
        n.enemies <- sample(1:3,1) # assume we randomly target between 1-3 enemies with the spell 
        i <- 1
        while (i <= n.enemies){
          saving.throw <- sample(1:20,1) + lvl.params$enemy.save.dex[row]
          if (saving.throw < dc){
            if (!("ff" %in% state$spells)){state$spells <- as.vector(c(na.omit(state$spells),"ff"))}
            state$concentration <- 1
            state$controlled <- 1
            state$ncontrolled <- state$ncontrolled + 1
          }
          i <- i + 1
        }
        rm(i,n.enemies,saving.throw)
    }
    
    # Hold Person (WIS)
    if (spell=="hp"){
      # spell targets # of enemies equal to spell level - 1 
      i <- 1 
      while (i <= (spell.lvl-1)){
        saving.throw <- sample(1:20,1) + lvl.params$enemy.save.wis[row]
        if (saving.throw < dc){
          if (!("hp" %in% state$spells)){state$spells <- as.vector(c(na.omit(state$spells),"hp"))}
          state$auto.crit <- 1 
          state$concentration <- 1
          state$controlled <- 1
          state$ncontrolled <- state$ncontrolled + 1
        }
        i <- i +1
      }
      rm(i,saving.throw)
    }
    
    # Blindness/Deafness (CON)
    if (spell=="bd"){
      # spell targets # of enemies equal to spell level - 1 
      i <- 1 
      while (i <= (spell.lvl-1)){
        saving.throw <- sample(1:20,1) + lvl.params$enemy.save.con[row]
        if (saving.throw < dc){
          if (!("bd" %in% state$spells)){state$spells <- as.vector(c(na.omit(state$spells),"bd"))}
          state$controlled <- 1
          state$ncontrolled <- state$ncontrolled + 1 
        }
        i <- i +1
      }
      rm(i,saving.throw)
    }
    
    # Bestow Curse (WIS)
    if (spell=="bc"){
      saving.throw <- sample(1:20,1) + lvl.params$enemy.save.wis[row]
      if (saving.throw < dc){
        state$spells <- as.vector(c(na.omit(state$spells),"bc"))
        if (spell.lvl < 5){
          state$cursed1 <- 1 
          state$concentration <- 1
        }
        if (spell.lvl >= 5){state$cursed0 <- 1}
      }
      rm(saving.throw)
    }
    
    # Greater Invisibility (None)
    if (spell=="gi"){
      state$spells <- as.vector(c(na.omit(state$spells),"gi"))
      state$concentration <- 1
      state$controlled <- 1
    }
    
    # Hold Monster (WIS)
    if (spell=="hm"){
      # spell targets # of enemies equal to spell level - 4 
      i <- 1 
      while (i <= (spell.lvl-4)){
        saving.throw <- sample(1:20,1) + lvl.params$enemy.save.wis[row]
        if (saving.throw < dc){
          if (!("hm" %in% state$spells)){state$spells <- as.vector(c(na.omit(state$spells),"hm"))}
          state$auto.crit <- 1 
          state$concentration <- 1
          state$controlled <- 1
          state$ncontrolled <- state$ncontrolled + 1 
        }
        i <- i +1
      }
      rm(i,saving.throw)
    }
    
    # The spells FoM and YRP don't do anything on cast, but grant states 
    # that convey damage riders to the attack action and CC enemies on/between
    # our turns
    
    # Fount of Moonlight
    if (spell=="fom"){
      # just start concentrating on it here, control occurs in between turns, damage rider on attack 
      state$spells <- as.vector(c(na.omit(state$spells),"fom"))
      state$concentration <- 1
    }
    
    # Yolande's Regal Presence (WIS)
    if (spell=="yrp"){
      state$spells <- as.vector(c(na.omit(state$spells),"yrp"))
      state$concentration <- 1 
    }
    
    return(state)
}

# Create function for updating state variables between turns
state.transition <- function(lvl){
  
  # update concentration and spell effects 
  if (state$concentration==1){
    # model concentration as a fixed probability increased by eldritch mind (if you have it)
    p <- global.params$pconc + as.numeric(lvl.params$eld.mind[which(lvl.params$lvl==lvl)]==1)*global.params$emb.pconc
    state$concentration <- rbinom(1,1,p)
    if (state$concentration==0){
      replace <- state$spells[!(state$spells %in% c("wb","thl","ff","hp","gi","fom","hm","yrp"))]
      if (length(replace)==0){replace <- NA}
      state$spells <- replace 
      state$witch.bolt1 <- 0 
      state$controlled <- 0 + as.numeric("bd" %in% state$spells)
      # account for bestow curse if it is cast with concentration 
      if (state$cursed1==1){
        state$spells <- state$spells[!(state$spells %in% c("bc"))]
        state$cursed1 <- 0
      }
    }
  }
 
  # allow for enemy saves on their turn (thl, bd, hp, hm)
  save.check <- as.numeric(sum(as.numeric(as.vector(unlist(lapply(as.list(c("thl","bd","hp","hm")), 
                                                                  function(x) return(x %in% state$spells))))))>=1)
  if (save.check==1){
    
    # get save DC from lvl.params 
    row <- which(lvl.params$lvl==lvl)
    dc <- 8 + lvl.params$pb[row] + lvl.params$attack.mod[row]
    
    # determine if it's a WIS or CON save 
    wis.check <- as.numeric(sum(as.numeric(as.vector(unlist(lapply(as.list(c("thl","hp","hm")), 
                                                                   function(x) return(x %in% state$spells))))))>=1)
    con.check <- as.numeric("bd" %in% state$spells)
    
    # roll a number of saving throws based on the number of controlled enemies 
    if (wis.check==1){
      for (i in 1:state$ncontrolled){
        saving.throw <- sample(1:20,1) + lvl.params$enemy.save.wis[row]
        if (saving.throw >= dc){
          state$ncontrolled <- state$ncontrolled-1
        }
        rm(i)
      }
    }
    if (con.check==1){
      for (i in 1:state$ncontrolled){
        saving.throw <- sample(1:20,1) + lvl.params$enemy.save.con[row]
        if (saving.throw >= dc){
          state$ncontrolled <- state$ncontrolled-1
        }
        rm(i)
      }
    }
    if (state$ncontrolled==0){
      state$controlled <- 0
      state$concentration <- 0 
      state$auto.crit <- 0 
    }
    rm(row,dc,wis.check,con.check)
  }
  rm(save.check)
  
  # deal with between turn effects of FoM 
  if ("fom" %in% state$spells){
    # set external probability of being attacked 
    ptargeted <- 0.5
    # determine whether or not we're attacked 
    targeted <- rbinom(1,1,ptargeted)
    # if attacked, have enemy make a saving throw 
    row <- which(lvl.params$lvl==lvl)
    dc <- 8 + lvl.params$pb[row] + lvl.params$attack.mod[row]
    saving.throw <- sample(1,1:20) + lvl.params$enemy.save.con[row]
    rm(row,dc)
    if (targeted==1 & saving.throw < dc){
      state$ncontrolled <- state$ncontrolled + 1 
      state$controlled <- 1
    }
    rm(ptargetd,targeted,saving.throw)
  }
  
  # update status of hex-blade's curse 
  if (state$hbcursed==1){state$hbcursed <- rbinom(1,1,prob=global.params$phbc)}
  
  # update status of vexed (models whether or not we're attacking same target)
  if (state$vexed==1){state$vexed <- rbinom(1,1,prob=global.params$pvex)}
  
  # update whether we have an external source of advantage or disadvantage 
  state$ext.adv <- rbinom(1,1,global.params$padv.ext)
  state$ext.dadv <- rbinom(1,1,global.params$pdis.ext)
  return(state)
}

# Create function to reset state to baseline 
state.reset <- function(){
  state$advantage <- 0 
  state$ext.adv <- 0
  state$disadvantage <- 0 
  state$ext.dadv <- 0 
  state$spells <- NA 
  state$concentration <- 0 
  state$vexed <- 0 
  state$hbcursed <- 0 
  state$controlled <- 0 
  state$ncontrolled <- 0 
  state$witch.bolt0 <- 0 
  state$witch.bolt1 <- 0 
  state$auto.crit <- 0 
  state$cursed0 <- 0 
  state$cursed1 <- 0 
  return(state)
}
  
# Create function for determining if attack roll has advantage or disadvantage based on state 
advantage <- function(){
  # first look at advantage 
    # do we have an external source of advantage?
    if (state$ext.adv==1){state$advantage <- 1}
    # is the enemy vexed?
    if (state$vexed==1){state$advantage <- 1}
    # is the enemy controlled?
    if (state$controlled==1){state$advantage <- 1}
  # factor in disadvantage 
    state$disadvantage <- state$ext.dadv
  # cancel out advantage/disadvantage if we have sources of both 
    if (state$advantage==1 & state$disadvantage==1){
      state$advantage <- 0 
      state$disadvantage <- 0 
    }
  # if use a luck point if we have them
    if (state$luck.pts>0 & state$advantage==0){
      state$advantage <- 1
      state$luck.pts <- state$luck.pts - 1
    }
  # return state 
    return(state)
}
  
# Create `single.attack` function
# just two-options -- either we use true-strike with hex-pistol, or we attack with witch bolt 
# need to update this to account for multiple sneak attack dice at later levels
single.attack <- function(lvl){
  
  # get enemy AC, proficiency bonus, and attack mod from lvl.params 
  row <- which(lvl.params$lvl==lvl)
  pb <- lvl.params$pb[row]
  mod <- lvl.params$attack.mod[row]
  ac <- lvl.params$enemy.ac[row]
  dc <- 8 + pb + mod
  
  # apply damage and controlled condition from Yolande's Regal Presence if we have it up
  yrp.dmg <- 0
  if ("yrp" %in% state$spells){
  saving.throw <- sample(1,1:20) + lvl.params$enemy.save.wis[row]
  if (saving.throw < dc){
    state$controlled <<- 1 
    state <<- state
    yrp.dmg <- sum(sample(1:6,1),
                   sample(1:6,1),
                   sample(1:6,1),
                   sample(1:6,1))
  }
  rm(saving.throw)
  }
  
  # determine if we have advantage on the attack 
  state <<- advantage() 
  
  # make attack roll vs. enemy AC 
  roll <- sample(1:20,1)
  if (state$advantage==1 | state$disadvantage==1){roll <- c(roll, sample(1:20,1))}
  if (state$disadvantage==1){roll <- min(roll)}
  
  # determine if you crit 
  crit <- sum(roll==20) + as.numeric(state$hbcursed==1)*sum(roll==19)
  crit <- as.numeric(crit>=1)
  if (state$auto.crit==1){crit <- 1}
  
  # determine if you hit 
  if (crit==1){hit <- 1}
  if (crit==0){hit <- as.numeric(max(roll)+pb+mod>=ac)}
  
  # compute different sources of damage
  
  # witch bolt initial attack damage 
  wb0.dmg <- (1 + crit)*state$witch.bolt0*sum(sample(1:12,1),sample(1:12,1))
  
  # witch bolt bonus action damage 
  wb1.dmg <- state$witch.bolt1*(1-state$witch.bolt0)*sample(1:12,1)
  wb1.dmg <- wb1.dmg + state$witch.bolt1*(1-state$witch.bolt0)*state$hbcursed*pb 
  wb1.dmg <- wb1.dmg + max(state$cursed0,state$cursed1)*sample(1:8,1)
  
  # weapon + sneak attack + piercer/charger damage 
  weap.dmg <- 0 
  {
    # first determine weapon die (wd)
    if (lvl.params$weapon[row]=="light.crossbow"){wd <- c(1:8)}
    if (lvl.params$weapon[row]=="pistol"){wd <- c(1:10)}
    if (lvl.params$weapon[row]=="musket"){wd <- c(1:12)}
    
    # roll weapon die
    wd.roll <- sample(wd,1)
    
    # roll again and take max if you have savage attacker
    if (lvl.params$svg.att[row]==1){wd.roll <- max(wd.roll,sample(wd,1))}
    
    # compute expected gain from reroll 
    gain <- mean(wd) - wd.roll
    
    # add a sneak attack die if we have advantage (HAVE TO UPDATE THIS)
    sneak <- 0
    wd.roll <- c(wd.roll,NA)
    gain <- c(gain,NA)
    if (state$advantage==1 & lvl>=2){
      sneak <- sample(1:6,1)
      wd.roll[2] <- sneak
      gain[2] <- 3.5-sneak
    }
    
    # add in charger damage die if we have charger feat 
    wd.roll <- c(wd.roll,NA)
    gain <- c(gain,NA)
    if (lvl.params$charge[row]==1){
      add.roll <- sample(1:8,1)
      wd.roll[3] <-add.roll
      gain[3] <- 4.5-add.roll
      rm(add.roll)
    }
    
    # if you crit, double the expected gain from rerolling on weapon/sneak attack dice 
    gain[which(is.na(gain)==F)] <- (1+crit)*gain[which(is.na(gain)==F)]
    
    # add additional damage die if you crit and have piercer feat 
    wd.roll <- c(wd.roll,NA)
    gain <- c(gain,NA)
    if (crit==1 & lvl.params$pierce[row]==1){
      add.roll <- sample(1:8,1)
      wd.roll[4] <-add.roll
      gain[4] <- 4.5-add.roll
      rm(add.roll)
    }
    
    # reroll one die with puncture if you have piercer feat 
    if (lvl.params$pierce[row]==1){
    reroll <- min(which(gain==max(gain,na.rm=T))) # just take min to get a single index, in case of ties 
    if (gain[reroll]>0){
      if (reroll==1){wd.rolls[1] <- sample(wd,1)}
      if (reroll==2){wd.rolls[2] <- sample(1:6,1)}
      if (reroll==3){wd.rolls[3] <- sample(1:8,1)}
      if (reroll==4){wd.rolls[4] <- sample(1:8,1)}
    }
    }
    
    # then sum non-NA weapon damage dice and double on crit 
    weap.dmg <- (1+crit)*sum(na.omit(wd.roll[1:3]))
    if (is.na(wd.roll[4])==F){weap.dmg <- weap.dmg + wd.roll[4]}
    weap.dmg <- weap.dmg*(1-state$witch.bolt0)
  }
  
  # true-strike additional damage
  {
  truestr.dmg <- 0 
  ndie <- lvl.params$true.strike[row]
  counter <- 1 
  while (counter <= ndie){
    truestr.dmg <- truestr.dmg + sample(1:6,1)
    counter <- counter + 1
  }
  truestr.dmg <- (1+crit)*(1-state$witch.bolt0)*truestr.dmg 
  }
  
  # fount of moonlight additional damage 
  # we don't actually ever get FoM damage until we're using multi-attack, 
  # since we aren't using melee weapons/making melee attacks 
  fom.dmg <- 0 
  if ("fom" %in% state$spell & lvl.params$weapon[row]=="rapier"){
    fom.dmg <- c(sample(1:6,1),
                 sample(1:6,1))
    fom.dmg <- (1-state$witch.bolt0)*(1+crit)*fom.dmg
  }
  
  # bestow curse damage 
  bc.dmg <- 0 
  if (state$cursed0==1 | state$cursed1==1){bc.dmg <- (1+crit)*sample(1:8,1)}
  
  # compute total dmg 
  spell.dmg <- yrp.dmg + hit*(wb0.dmg + truestr.dmg + fom.dmg + bc.dmg) + wb1.dmg 
  weap.dmg <- hit*weap.dmg 
  flat.dmg <- hit*(state$hbcursed*pb + (1-state$witch.bolt0)*mod)
  dmg <- spell.dmg + weap.dmg + flat.dmg 
  spell.share <- NA 
  weap.share <- NA 
  flat.share <- NA 
  if (dmg>0){
  spell.share <- spell.dmg/dmg 
  weap.share <- weap.dmg/dmg 
  flat.share <- flat.dmg/dmg
  }
  
  # update status effects based on hit 
  state$vexed <- (1-state$witch.bolt0)*as.numeric(lvl>=2)*hit
  state <<- state
  if(state$witch.bolt0==1){
    state$witch.bolt0 <- 0
    state <<- state
  }
  
  # return outputs 
  outcomes <- list(state,
                   state$advantage,
                   state$disadvantage,
                   hit,crit,spell.share,weap.share,flat.share,dmg)
  names(outcomes) <- c("state","adv","dadv","hit","crit","spell.share","weap.share","flat.share","dmg")
  return(outcomes)
}

# Create function that produces outcomes object in the even that you cast a spell 
null.outcomes <- function(env){
  state <- get("state",envir = env)
  outcomes <- list(state,
                   state$advantage,
                   state$disadvantage,
                   0,0,NA,NA,NA,0)
  names(outcomes) <- c("state","adv","dadv","hit","crit","spell.share","weap.share","flat.share","dmg")
  return(outcomes)
}

# Create a function for summarizing the state after each round of combat 
state.summarize <- function(df,outcomes){
  # Check if df is NULL
  if (is.null(df)) {
    # initialize data.frame for storing results 
    df <- data.frame("hit" = outcomes$hit,
                     "crit" = outcomes$crit,
                     "noncrit.dmg" = (1-outcomes$crit)*outcomes$dmg,
                     "crit.dmg" = outcomes$crit*outcomes$dmg,
                     "avg.dmg" = outcomes$dmg,
                     "spell.share" = outcomes$spell.share,
                     "weap.share" = outcomes$weap.share,
                     "flat.share" = outcomes$flat.share,
                     "adv" = outcomes$state$advantage,
                     "dis" = outcomes$state$disadvantage,
                     "neutral" = as.numeric(outcomes$state$advantage==0 & outcomes$state$disadvantage==0),
                     "vexed"= outcomes$state$vexed,
                     "controlled"=outcomes$state$controlled,
                     "luck.pts" = outcomes$state$luck.pts,
                     "hbcursed" = outcomes$state$hbcursed,
                     "concentr"= outcomes$state$concentration,
                     "wb" = outcomes$state$witch.bolt1,
                     "thl" = as.numeric("thl" %in% outcomes$state$spells),
                     "ff" = as.numeric("ff" %in% outcomes$state$spells),
                     "bd" = as.numeric("bd" %in% outcomes$state$spells),
                     "hp" = as.numeric("hp" %in% outcomes$state$spells),
                     "bc" = as.numeric("bc" %in% outcomes$state$spells),
                     "gi" = as.numeric("gi" %in% outcomes$state$spells),
                     "hm" = as.numeric("hm" %in% outcomes$state$spells),
                     "fom" = as.numeric("fom" %in% outcomes$state$spells),
                     "yrp" = as.numeric("yrp" %in% outcomes$state$spells))
  } else {
    # create a new row of summary results 
    new.row <- c(outcomes$hit,
                 outcomes$crit,
                 (1-outcomes$crit)*outcomes$dmg,
                 outcomes$crit*outcomes$dmg,
                 outcomes$dmg,
                 outcomes$spell.share,
                 outcomes$weap.share,
                 outcomes$flat.share,
                 outcomes$state$advantage,
                 outcomes$state$disadvantage,
                 as.numeric(outcomes$state$advantage==0 & outcomes$state$disadvantage==0),
                 outcomes$state$vexed,
                 outcomes$state$controlled,
                 outcomes$state$luck.pts,
                 outcomes$state$hbcursed,
                 outcomes$state$concentration,
                 outcomes$state$witch.bolt1,
                 as.numeric("thl" %in% outcomes$state$spells),
                 as.numeric("ff" %in% outcomes$state$spells),
                 as.numeric("bd" %in% outcomes$state$spells),
                 as.numeric("hp" %in% outcomes$state$spells),
                 as.numeric("bc" %in% outcomes$state$spells),
                 as.numeric("gi" %in% outcomes$state$spells),
                 as.numeric("hm" %in% outcomes$state$spells),
                 as.numeric("fom" %in% outcomes$state$spells),
                 as.numeric("yrp" %in% outcomes$state$spells))
    # Add the new row to the existing dataframe
    df <- rbind(df, new.row)
  }
  return(df)
}

# Simulate level-1 damage  (Warlock-01)
# battle plan = cast witch bolt at start of first two combats, then attack
parent <- parent.frame()
nsim <- 10000 
battle.plan0 <- function(lvl,env){
  # reset state 
  state <<- state.reset()
  
  # reset luck points
  state$luck.pts <- lvl.params$pb[which(lvl.params$lvl==lvl)]
  state <<- state 
  
  # COMBAT 1 
  {
  # Turn 1 
  
    # cast witch bolt
    state <<- cast.spell(lvl,"wb",1)
    
    # make single attack 
    out <- single.attack(lvl)
   
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(NULL,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
  
  # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
  # Turn 3 
  
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
  # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # SHORT REST (recover spell slots)
  
  # COMBAT 2 
  {
  # reset state
    state <<- state.reset()
    
  # Turn 1 
    
    # cast witch bolt
    state <<- cast.spell(lvl,"wb",1)
  
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
  # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
  # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
  # Turn 4 
   
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # COMBAT 3 (no spell slots left)
  {
  # reset state
    state <<- state.reset()
    
  # Turn 1 
   
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
  # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
  # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
  # Turn 4 

    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # Return combat results 
    results.df$luck.pts <- rep(min(results.df$luck.pts),nrow(results.df)) # only care if we're using them all or not
    return(results.df)
}
summary <- as.data.frame(t(as.matrix(apply(do.call("rbind",lapply(as.list(1:nsim),
                                                                    function(x) battle.plan0(1,parent))),
                                     2,function(x) mean(x,na.rm=T)))))


# Simulate level-2 damage (Warlock-01, Rogue-01)
# battle plan is the same; we gain weapon mastery and sneak attack 
parent <- parent.frame()
nsim <- 10000 
battle.plan0 <- function(lvl,env){
  # reset state 
  state <<- state.reset()
  
  # reset luck points
  state$luck.pts <- lvl.params$pb[which(lvl.params$lvl==lvl)]
  state <<- state 
  
  
  # COMBAT 1 
  {
    # Turn 1 
    
    # cast witch bolt
    state <<- cast.spell(lvl,"wb",1)
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(NULL,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # SHORT REST (recover spell slots)
  
  # COMBAT 2 
  {
    # reset state
    state <<- state.reset()
    
    # Turn 1 
    
    # cast witch bolt
    state <<- cast.spell(lvl,"wb",1)
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # COMBAT 3 (no spell slots left)
  {
    # reset state
    state <<- state.reset()
    
    # Turn 1 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # Return combat results 
  results.df$luck.pts <- rep(min(results.df$luck.pts),nrow(results.df)) # only care if we're using them all or not
  return(results.df)
}
add.row <- as.data.frame(t(as.matrix(apply(do.call("rbind",lapply(as.list(1:nsim),
                                                                  function(x) battle.plan0(2,parent))),
                                           2,function(x) mean(x,na.rm=T)))))
summary <- rbind(summary,add.row)
rm(add.row)
gc()


# Simulate level-3 damage (Warlock-02, Rogue-01)
# gain savage attacker; switch battle plan: now we cast faerie fire at the start of each of the first 2 combats 
# in the third combat, we alternate between casting faerie fire and just starting to attack
parent <- parent.frame()
nsim <- 10000 
battle.plan1 <- function(lvl,env){
  # reset state 
  state <<- state.reset()
  
  # reset luck points
  state$luck.pts <- lvl.params$pb[which(lvl.params$lvl==lvl)]
  state <<- state 
  
  
  # COMBAT 1 
  {
    # Turn 1 
    
    # cast faerie fire and update advantage
    state <<- cast.spell(lvl,"ff",1)
    state <<- advantage()
    
    # generate null outcomes 
    out <- null.outcomes(env)
    
    # get state post spell
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(NULL,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # COMBAT 2 
  {
    # reset state
    state <<- state.reset()
    
    # Turn 1 
    
    # cast faerie fire and update advantage
    state <<- cast.spell(lvl,"ff",1)
    state <<- advantage()
    
    # generate null outcomes
    out <- null.outcomes(env)
    
    # get state post spell
    state <<- out$state
   
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # COMBAT 3
  {
    # reset state
    state <<- state.reset()
    
    # Turn 1 
    switch <- rbinom(1,1,prob=0.5)
    # either cast faerie fire or make single attack 
    if (switch==0){
    # cast faerie fire and update advantage
    state <<- cast.spell(lvl,"ff",1)
    state <<- advantage()
    
    # generate null outcomes 
    out <- null.outcomes(env)
    }
    if (switch==1){
    # make single attack 
    out <- single.attack(lvl)
    }
    
    # get state post spell/attack
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # Return combat results 
  results.df$luck.pts <- rep(min(results.df$luck.pts),nrow(results.df)) # only care if we're using them all or not
  return(results.df)
}
add.row <- as.data.frame(t(as.matrix(apply(do.call("rbind",lapply(as.list(1:nsim),
                                                                  function(x) battle.plan1(3,parent))),
                                           2,function(x) mean(x,na.rm=T)))))
summary <- rbind(summary,add.row)
rm(add.row)
gc()


# Simulate level-4 damage (Warlock-03, Rogue-01)
# battle plan: for 1st and 2nd combat, alternate between opening with faerie fire and opening with 
# an attack, using hbcurse as a BA. In third combat open with faerie fire and then attack. 
parent <- parent.frame()
nsim <- 10000 
battle.plan2 <- function(lvl,env){
  # reset state 
  state <<- state.reset()
  
  # reset luck points
  state$luck.pts <- lvl.params$pb[which(lvl.params$lvl==lvl)]
  state <<- state 
  
  # COMBAT 1 
  {
    # Turn 1
    
    # bonus action hexblade's curse 
    state$hbcursed <- 1
    state <<- state
    
    # then either cast faerie fire or make single attack 
    switch <- rbinom(1,1,prob=0.5)
    if (switch==0){
      # cast faerie fire and update advantage
      state <<- cast.spell(lvl,"ff",1)
      state <<- advantage()
      
      # generate null outcomes 
      out <- null.outcomes(env)
    }
    if (switch==1){
      # make single attack 
      out <- single.attack(lvl)
    }
    
    # get state post spell/attack
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(NULL,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # SHORT REST (Recover Hexblade's Curse)
  
  # COMBAT 2 
  {
    # reset state
    state <<- state.reset()
    
    # Turn 1
    
    # bonus action hexblade's curse 
    state$hbcursed <- 1
    state <<- state
    
    # then either cast faerie fire or make single attack 
    switch <- rbinom(1,1,prob=0.5)
    if (switch==0){
      # cast faerie fire and update advantage
      state <<- cast.spell(lvl,"ff",1)
      state <<- advantage()
      
      # generate null outcomes 
      out <- null.outcomes(env)
    }
    if (switch==1){
      # make single attack 
      out <- single.attack(lvl)
    }
    
    # get state post spell/attack
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # COMBAT 3
  {
    # reset state
    state <<- state.reset()
    
    # Turn 1 
    
    # cast faerie fire and update advantage
    state <<- cast.spell(lvl,"ff",1)
    state <<- advantage()
    
    # generate null outcomes 
    out <- null.outcomes(env)
    
    # get state post spell
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # Return combat results 
  results.df$luck.pts <- rep(min(results.df$luck.pts),nrow(results.df)) # only care if we're using them all or not
  return(results.df)
}
add.row <- as.data.frame(t(as.matrix(apply(do.call("rbind",lapply(as.list(1:nsim),
                                                                  function(x) battle.plan2(4,parent))),
                                           2,function(x) mean(x,na.rm=T)))))
summary <- rbind(summary,add.row)
rm(add.row)
gc()


# Simulate level-5 damage (Warlock-04, Rogue-01)
# battle plan is the same as lvl-04
parent <- parent.frame()
nsim <- 10000 
battle.plan2 <- function(lvl,env){
  # reset state 
  state <<- state.reset()
  
  # reset luck points
  state$luck.pts <- lvl.params$pb[which(lvl.params$lvl==lvl)]
  state <<- state 
  
  # COMBAT 1 
  {
    # Turn 1
    
    # bonus action hexblade's curse 
    state$hbcursed <- 1
    state <<- state
    
    # then either cast faerie fire or make single attack 
    switch <- rbinom(1,1,prob=0.5)
    if (switch==0){
      # cast faerie fire and update advantage
      state <<- cast.spell(lvl,"ff",1)
      state <<- advantage()
      
      # generate null outcomes 
      out <- null.outcomes(env)
    }
    if (switch==1){
      # make single attack 
      out <- single.attack(lvl)
    }
    
    # get state post spell/attack
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(NULL,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # SHORT REST (Recover Hexblade's Curse)
  
  # COMBAT 2 
  {
    # reset state
    state <<- state.reset()
    
    # Turn 1
    
    # bonus action hexblade's curse 
    state$hbcursed <- 1
    state <<- state
    
    # then either cast faerie fire or make single attack 
    switch <- rbinom(1,1,prob=0.5)
    if (switch==0){
      # cast faerie fire and update advantage
      state <<- cast.spell(lvl,"ff",1)
      state <<- advantage()
      
      # generate null outcomes 
      out <- null.outcomes(env)
    }
    if (switch==1){
      # make single attack 
      out <- single.attack(lvl)
    }
    
    # get state post spell/attack
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # COMBAT 3
  {
    # reset state
    state <<- state.reset()
    
    # Turn 1 
    
    # cast faerie fire and update advantage
    state <<- cast.spell(lvl,"ff",1)
    state <<- advantage()
    
    # generate null outcomes 
    out <- null.outcomes(env)
    
    # get state post spell
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # Return combat results 
  results.df$luck.pts <- rep(min(results.df$luck.pts),nrow(results.df)) # only care if we're using them all or not
  return(results.df)
}
add.row <- as.data.frame(t(as.matrix(apply(do.call("rbind",lapply(as.list(1:nsim),
                                                                  function(x) battle.plan2(5,parent))),
                                           2,function(x) mean(x,na.rm=T)))))
summary <- rbind(summary,add.row)
rm(add.row)
gc()


# Simulate level-6 damage (Warlock-04, Rogue-01, Bard-01)
# bard-01 gives us some additional spell slots; with these, assume we weave in some hold-persons
# in addition to casting faerie fire for control
parent <- parent.frame()
nsim <- 10000 
battle.plan3 <- function(lvl,env){
  # reset state 
  state <<- state.reset()
  
  # reset luck points
  state$luck.pts <- lvl.params$pb[which(lvl.params$lvl==lvl)]
  state <<- state 
  
  
  # COMBAT 1 
  {
    # Turn 1
    
    # bonus action hexblade's curse 
    state$hbcursed <- 1
    state <<- state
    
    # then either cast faerie fire, hold-person, or make single attack 
    switch <- sample(1:3,1)
    if (switch==1){
      # cast faerie fire and update advantage
      state <<- cast.spell(lvl,"ff",1)
      state <<- advantage()
      
      # generate null outcomes 
      out <- null.outcomes(env)
    }
    if (switch==2){
      # cast hold person and update advantage
      state <<- cast.spell(lvl,"hp",2)
      state <<- advantage()
      
      # generate null outcomes 
      out <- null.outcomes(env)
    }
    if (switch==3){
      # make single attack 
      out <- single.attack(lvl)
    }
    
    # get state post spell/attack
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(NULL,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # SHORT REST (Recover Hexblade's Curse)
  
  # COMBAT 2 
  {
    # reset state
    state <<- state.reset()
    
    # Turn 1
    
    # bonus action hexblade's curse 
    state$hbcursed <- 1
    state <<- state
    
    # then either cast faerie fire, hold-person, or make single attack 
    switch <- sample(1:3,1)
    if (switch==1){
      # cast faerie fire and update advantage
      state <<- cast.spell(lvl,"ff",1)
      state <<- advantage()
      
      # generate null outcomes 
      out <- null.outcomes(env)
    }
    if (switch==2){
      # cast hold person and update advantage
      state <<- cast.spell(lvl,"hp",2)
      state <<- advantage()
      
      # generate null outcomes 
      out <- null.outcomes(env)
    }
    if (switch==3){
      # make single attack 
      out <- single.attack(lvl)
    }
    
    # get state post spell/attack
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # COMBAT 3
  {
    # reset state
    state <<- state.reset()
    
    # Turn 1 
    
    # either cast faerie fire, hold-person, or make single attack 
    switch <- sample(1:3,1)
    if (switch==1){
      # cast faerie fire and update advantage
      state <<- cast.spell(lvl,"ff",1)
      state <<- advantage()
      
      # generate null outcomes 
      out <- null.outcomes(env)
    }
    if (switch==2){
      # cast hold person and update advantage
      state <<- cast.spell(lvl,"hp",2)
      state <<- advantage()
      
      # generate null outcomes 
      out <- null.outcomes(env)
    }
    if (switch==3){
      # make single attack 
      out <- single.attack(lvl)
    }
    
    # get state post spell/attack
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 2 
    state <<- state.transition(lvl)
    
    # Turn 2 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 3 
    state <<- state.transition(lvl)
    
    # Turn 3 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
    
    # transition to turn 4 
    state <<- state.transition(lvl)
    
    # Turn 4 
    
    # make single attack 
    out <- single.attack(lvl)
    
    # get state post attack 
    state <<- out$state
    
    # summarize state post attack 
    results.df <- state.summarize(results.df,out)
  }
  
  # Return combat results 
  results.df$luck.pts <- rep(min(results.df$luck.pts),nrow(results.df)) # only care if we're using them all or not
  return(results.df)
}
add.row <- as.data.frame(t(as.matrix(apply(do.call("rbind",lapply(as.list(1:nsim),
                                                                  function(x) battle.plan3(6,parent))),
                                           2,function(x) mean(x,na.rm=T)))))
summary <- rbind(summary,add.row)
rm(add.row)
gc()



  
# Quicksave 
setwd("C:/Users/cmaue/OneDrive/Desktop/desktemp/theory_craft/dnd_chars/2024_PHB/_temp")
save.image(file = "quicksave.RData")
load("quicksave.RData")


  

# multi.attack = hex.pistol + thorn.whip (spell damage riders)




##########################################################################################################################
### OLD NOTES 
{
# Modeling advantage 
# (1)
# start with two fixed baseline probabilities: (i) the probability that an ally or other external 
# factor gives you advantage on an attack and (ii) the probability that an enemy or other external 
# factor gives you disadvantage on an attack. 
# (2)
# factor in the increased chance of having advantage granted by control spells. We assume three 
# categories of control spells (low, medium, high) which increase the probability that we have 
# advantage on attacks by different fixed amounts. Note this increased benefit depends on whether 
# or not we are able to maintain concentration
# (3)
# factor in the probability of having advantage on an attack based on whether or not the attack 
# is against a `vexed` target (i.e., whether the attack has inherited the vex parameter from a 
# previous turn/attack)
# (4) 
# factor in luck points. Assume that if we do not have advantage from another source and we 
# have luck points available, then we will use those luck points to give ourselves advantage. 
# 
# NOTE: none of the factors (1)-(3) have probabilities set equal to 1 even when there's no 
# save/uncertainty involved in the mechanism that grants advantage. This is done to account
# for the fact that you might kill targets, switch targets, or your targets might take actions
# which nullify your advantage against them.

# Modeling hexblade's curse 
# if we attack on the turn that we use hexblades curse, we assume the hbcurse condition occurs with
# probability = 1 
# on subsequent turns, we assume there's a fixed probability that we continue attacking the cursed 
# target (either because they die, or we attack a different target)
# we model this as two distinct parameters:
# hbc0 = hexblade's curse on the turn we apply it, applies the cursed condition with probability = 1 
# hbc1 = hexblade's curse on subsequent turns, applies the cursed condition with prob < 1 
# we start with a stock of 2 uses of hbc0 (2 per LR assuming 1 SR/day), and assume we use 1 at the start 
# of the first two combats of each day. At character lvl-15 (when we get prayer of healing) we increase 
# the stock to 3 and use it at the start of each combat. No need to model as a state variable 

# Other stock variables 
# luck points: start with a number = to your PB, decrease with each use until 0 
# puncture reroll: by default we use this in the most optimal way given our attacks
# savage attacker reroll: by default we use this on our only weapon attack roll each turn 
  
  
  
t <- expand.grid(c(1:10),c(1:10))
t <- as.data.frame(t)
colnames(t) <- c("die1","die2")
t <- t[order(t$die1,t$die2),]
t$max <- as.vector(unlist(apply(t,1,function(x) max(x))))
sum(t$max)/100
tt <- expand.grid(as.vector(t$max),c(1:10))
tt <- as.data.frame(tt)
colnames(tt) <- c("savage.att","piercer")
tt$die1 <- as.vector(unlist(apply(tt,1,function(x) max(x))))
tt$die2 <- as.vector(unlist(apply(tt,1,function(x) min(x))))
tt$die2[which(tt$die2<5)] <- 5.5
tt$sum <- tt$die1 + tt$die2 
sum(tt$sum)/nrow(tt)


hex.pistol <- function(wd,svgatt,sneak,pierce,crit,mod,hbc){
  # for non-crits 
  if (crit==0){
    # roll weapon die (wd) 
    d1 <- sample(wd,1)
    # roll again and take max if you have svgatt
    if (svgatt==1){d1 <- max(d1,sample(wd,1))}
    # if you have sneak attack, roll a d6
    d2 <- NA
    if (sneak==1){d2 <- sample(c(1:6),1)}
    # determine worst roll as measured by deviation from average result
    dev1 <- d1-mean(wd)
    dev2 <- NA 
    if (sneak==1){dev2 <- d2-mean(c(1:6))}
    devs <- na.omit(c(dev1,dev2))
    # if roll is less than average result, then reroll the one that is the furthest below
    # if you have piercer
    if (pierce==1){
      reroll <- which(devs==min(devs))
      if (length(reroll>1)){reroll <- reroll[1]}
      if (devs[reroll]<0){
        if (reroll==1){d1 <- sample(wd,1)}
        if (reroll==2){d2 <- sample(c(1:6),1)}
      }
    }
    # sum damage rolls 
    dice.dmg <- sum(na.omit(c(d1,d2)))
  }
  # for crits 
  if (crit==1){
    # roll weapon die (wd) 
    d1 <- sample(wd,1)
    # roll again and take max if you have svgatt
    if (svgatt==1){d1 <- max(d1,sample(wd,1))}
    # if you have sneak attack, roll a d6
    d2 <- NA
    if (sneak==1){d2 <- sample(c(1:6),1)}
    # roll additional damage die from piercer (if you have it)
    d3 <- NA 
    if (pierce==1){d3 <- sample(wd,1)}
    # determine worst roll as measured by deviation from average result
    dev1 <- d1-mean(wd)
    dev2 <- NA 
    if (sneak==1){dev2 <- d2-mean(c(1:6))}
    dev3 <- NA 
    if (pierce==1){dev3 <- (d3-mean(wd))/2} # divide by 2 since we don't double the extra die, making the reroll half as valuable
    devs <- na.omit(c(dev1,dev2,dev3))
    # if roll is less than average result, then reroll the one that is the furthest below
    # if you have piercer
    if (pierce==1){
      reroll <- which(devs==min(devs))
      if (length(reroll>1)){reroll <- reroll[1]}
      if (devs[reroll]<0){
        if (reroll==1){d1 <- sample(wd,1)}
        if (reroll==2){d2 <- sample(c(1:6),1)}
        if (reroll==3){d3 <- sample(wd,1)}
      }
    }
    # sum damage rolls and double then add extra die 
    dice.dmg <- 2*sum(na.omit(c(d1,d2)))
    if (pierce==1){dice.dmg <- dice.dmg + d3}
  }
  # add attack mod and hexblade's curse (if applicable)
  dmg <- dice.dmg 
  if (hbc>0){dmg <- dmg + hbc}
  dmg <- dmg + mod
  return(dmg)
}
nsim <- 100000
d10 <- c(1:10)

# non-crits 
# no savage attacker, no sneak attack, no piercer, non-crit, no hexblade's curse, no attack mod
# average result should be 5.5 on a d10 
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,0,0,0,0,0,0))))) # 5.5 

# add in savage attacker, result should be 7.15
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,0,0,0,0,0))))) # 7.15

# so savage attacker adds 1.65 damage

# add piercer in w/o sneak attack, result should be ~7.65
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,0,1,0,0,0))))) # 7.56

# so without sneak attack, piercer only adds an additional 0.41 to our pistol damage on top of savage attacker

# now look at sneak attack w/o piercer, result should be 10.65
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,1,0,0,0,0))))) # 10.65

# then look at what it is with piercer and sneak attack 
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,1,1,0,0,0))))) # 11.70

# so piercer adds about 1 damage. Together, piercer and savage attacker add about 2.65 on non-crits 
# basically an additional d4 in damage, passively

# add in attack mod 
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,1,1,0,4,0))))) # 15.68

# add in hexblade's curse 
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,1,1,0,4,4))))) # 19.68

# crits 
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,0,0,0,1,0,0))))) # 11 (baseline)
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,0,0,1,0,0))))) # 14.3 (+ savage attacker)
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,1,0,1,0,0))))) # 21.3 (+ savage attacker, sneak attack)
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,1,1,1,0,0))))) # 29.54 (+ savage attacker, sneak attack, piercer)
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,1,1,1,4,0))))) # 33.56 (+ savage attacker, sneak attack, piercer, mod)
t <- mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,1,1,1,4,4))))) # 37.56 (+ savage attacker, sneak attack, piercer, mod, hbc)

# So then our `average damage`, based on the way we level is 
# with piercer: 
0.2*44.6 + 0.8*23.2 # 27.48

# without piercer 
t <-  mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,1,0,1,4,4))))) # 29.27 (+ savage attacker, sneak attack, mod, hbc)
t <-  mean(as.vector(unlist(lapply(as.list(1:nsim), function(x) hex.pistol(d10,1,1,0,0,4,4))))) # 18.65 (+ savage attacker, sneak attack, mod, hbc)
0.2*36.25 + 0.8*22.15 # 24.97

# difference = 2.482
}











