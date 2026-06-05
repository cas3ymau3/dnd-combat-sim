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

# Point-Buy Stats 
  # STR = 14 (+2) = 16
  # DEX = 13 
  # CON = 13 (+1) = 14
  # INT = 8
  # WIS = 13
  # CHA = 13

# Species: Orc 
 # Origin feats: tough  

# Weapon(s)
 # greatsword = 2d6 slashing (graze); heavy, two-handed 
 # maul = 2d6 bludgeoning (topple); heavy, two-handed 

# Build:
  # lvl-01: paladin-01 -------------------------------------------------> tough, heavy armor, divine favor/smite
  # lvl-02: paladin-01, ranger-01 --------------------------------------> favored enemy
  # lvl-03: paladin-01, ranger-02 --------------------------------------> deft explorer, great weapon fighting   
  # lvl-04: paladin-01, ranger-03 (hunter) -----------------------------> hunter's prey, colossus slayer
  # lvl-05: paladin-01, ranger-04 (hunter) -----------------------------> great weapon master (STR=17)
  # lvl-06: paladin-01, ranger-05 (hunter) -----------------------------> extra attack
  # lvl-07: paladin-01, ranger-06 (hunter) -----------------------------> roving
  # lvl-08: paladin-01, ranger-07 (hunter) -----------------------------> defensive tactics
  # lvl-09: paladin-01, ranger-08 (hunter) -----------------------------> ASI: STR=18, WIS=14
  # lvl-10: paladin-01, ranger-09 (hunter) -----------------------------> expertise, elemental weapon 
  # lvl-11: paladin-02, ranger-09 (hunter) -----------------------------> channel divinity, paladin smite, defensive
  # lvl-12: paladin-03 (devotion), ranger-09 (hunter) ------------------> sacred weapon 
  # lvl-13: paladin-04 (devotion), ranger-09 (hunter) ------------------> ASI: STR=20
  # lvl-14: paladin-04 (devotion), ranger-09 (hunter), cleric-1 --------> divine order: thaumaturge 
  # lvl-15: paladin-04 (devotion), ranger-09 (hunter), cleric-2 --------> channel divinity, 5th lvl slot
  # lvl-16: paladin-04 (devotion), ranger-09 (hunter), cleric-3 (war) --> guided strike, war priest
  # lvl-17: paladin-04 (devotion), ranger-09 (hunter), cleric-4 (war) --> resilient, CON=15 
  # lvl-18: paladin-04 (devotion), ranger-09 (hunter), cleric-5 (war) --> sear undead 
  # lvl-19: paladin-04 (devotion), ranger-09 (hunter), cleric-6 (war) --> war god's blessing, 7th lvl slot
  # lvl-20: paladin-04 (devotion), ranger-09 (hunter), cleric-7 (war) --> blessed strikes

# ASSUMPTIONS 
 # (1)
 # 4 combats per day, 4 rounds per combat, 1 short rest per day 
 # (2) 
 # If using maul, prone targets 50% of the time, and enemies stand up on their turn
 # (3)
 # GWF applies to damage from (i) weapon, (ii) divine favor, (iii) elemental weapon, and (iv) colossus slayer 
 # (4)
 # With CON=14, we maintain concentration 80% of the time levels 1-5, 75% of the time levels 6-12, and 70% of the time levels 13-17
 # (5) 
 # You are able to make an attack of opportunity (OA) in 25% of combat rounds

# HP calculation 
{
  # lvl-1 = max hit.die + CON = 10+2 = 12+2(tough) = 14
  # paladin/ranger levels add 1d10+2 = 7.5 avg 
  # cleric levels add 1d8+2 = 6.5 avg
  init <- rep(14,13)
  add <- c(0:12)*rep(7.5,13)
  hp13 <- init + add
  init2 <- rep(hp13[13],7)
  add2 <- c(1:7)*rep(6.5,7)
  hp2 <- init2 + add2
  hp <- c(hp13,hp2)
  rm(init,add,hp13,add2,init2,hp2)
}

# Create dataframe to store results 
{
results.df <- data.frame("lvl"=1:20,
                         "feat.ASI"=c("Tough, Heavy Armor, Divine Favor/Smite",
                                      "Favored Enemy",
                                      "Deft Explorer, GWF",
                                      "Hunter's Lore, Hunter's Prey (Colossus Slayer)",
                                      "GWM (STR=17)",
                                      "Extra Attack",
                                      "Roving",
                                      "Defensive Tactics (Multi-Attack Defense)",
                                      "ASI: +1 STR (STR=18), +1 WIS (WIS=14)",
                                      "Expertise, Elemental Weapon",
                                      "Channel Divinity (P), Paladin's Smite, Defensive",
                                      "Sacred Weapon",
                                      "ASI: +2 STR (STR=20)",
                                      "Divine Order: Thaumaturge",
                                      "Channel Divinity (C), 5th lvl Slot",
                                      "Guided Strike, War Priest",
                                      "Resilient CON (CON=15)",
                                      "Sear Undead",
                                      "War God's Blessing, 7th lvl Slot",
                                      "Blessed Strikes"),
                         "PB"=c(rep(2,4),rep(3,4),rep(4,4),rep(5,4),rep(6,4)),
                         "STR"=c(rep(16,4),rep(17,4),rep(18,4),rep(20,8)),
                         "armor"=c(rep("Chain Mail",5),rep("Splint Armor",6),rep("Plate Armor",9)),
                         "AC"=c(rep(16,5),rep(17,5),18,rep(19,9)),
                         "HP"=hp,
                         "hit.dice"=c("1d10","2d10","3d10","4d10","5d10","6d10","7d10","8d10","9d10","10d10",
                                      "11d10","12d10","13d10","13d10,1d8","13d10,2d8","13d10,3d8","13d10,4d8",
                                      "13d10,5d8","13d10,6d8","13d10,7d8"),
                         "spell.slots"=c("2","3","3","4-2","4-2","4-3","4-3","4-3-2","4-3-2","4-3-3","4-3-3",
                                         "4-3-3-1","4-3-3-1","4-3-3-2","4-3-3-3-1","4-3-3-3-2","4-3-3-3-2-1",
                                         "4-3-3-3-2-1","4-3-3-3-2-1-1","4-3-3-3-2-1-1"),
                         "enemy.AC"=c(rep(13,3),14,rep(15,3),rep(16,2),rep(17,3),rep(18,4),rep(19,2),rep(20,2)))
results.df$EDPR <- NA 
rm(hp)
}

# Create functions to compute expected value of a single attack 
single.attack <- function(parameters){
  
# unpack parameters
  wd        <- parameters$weapon.die
  gwf       <- parameters$great.weapon.fighting
  gwm       <- parameters$great.weapon.master
  topl      <- parameters$topple
  ptopl     <- parameters$topple.prob
  grze      <- parameters$graze
  str       <- parameters$strength
  pb        <- parameters$proficiency.bonus
  df        <- parameters$divine.favor
  ds        <- parameters$divine.smite # level of divine smite spell
  cs        <- parameters$colossus.slayer
  ew        <- parameters$elemental.weapon # level of elemental weapon spell
  hm        <- parameters$hunters.mark
  sw        <- parameters$sacred.weapon
  gs        <- parameters$guided.strike
  bs        <- parameters$blessed.strike
  eac       <- parameters$enemy.ac 
  adv       <- parameters$advantage
 
 # roll d20 (with advantage if specified)
  d20 <- sample(1:20,1)
  if (adv==1){
    d20a <- sample(1:20,1)
    d20 <- max(d20,d20a)
    rm(d20a)
  }
  
 # determine attack bonus 
  ewb <- 1*as.numeric(ew>=3 & ew<5) + 2*as.numeric(ew>=5 & ew<7) + 3*as.numeric(ew==7) # bonus to attack rolls from elemental weapon
  ab <- pb + str + 1*as.numeric(sw==1) + ewb + 10*as.numeric(gs==1)
  
 # determine attack roll and crit status  
  ar <- d20 + ab 
  if (d20==1){ar <- 0} # nat 1's always miss 
  if (d20==20){ar <- 100} # nat 20's always hit (AC<=100)
  
 # compute damage if attack hits 
  dmg <- str*as.numeric(grze==1) # 0 or graze dmg if attack misses 
  topple <- 0 
  if (ar >= eac){
    
    # set up extra damage die 
    df.die <- 1:4
    ds.die <- 1:8
    cs.die <- 1:8
    ew.die <- 1:4
    hm.die <- 1:6
    bs.die <- 1:8
    
    # modify die given gwf status 
    if (gwf==1){
      wd[wd<3] <- 3
      df.die[df.die<3] <- 3
      cs.die[cs.die<3] <- 3
      ew.die[ew.die<3] <- 3
    }
    
    # compute dice roll damage 
    dmg <- sample(wd,1) + sample(wd,1) #2d6
    if (df==1){dmg <- dmg + sample(df.die,1)}
    if (hm==1){dmg <- dmg + sample(hm.die,1)}
    if (cs==1){dmg <- dmg + sample(cs.die,1)}
    if (bs==1){dmg <- dmg + sample(bs.die,1)}
    # elemental weapon extra damage 
    if (ew>=3 & ew<5){dmg <- dmg + sample(ew.die,1)}
    if (ew>=5 & ew<7){dmg <- dmg + sample(ew.die,1) + sample(ew.die,1)}
    if (ew==7){dmg <- dmg + sample(ew.die,1) + sample(ew.die,1) + sample(ew.die,1)}
    # divine smite extra damage 
    if (ds>=1){
      ds.dmg <- sample(ds.die,1) + sample(ds.die,1)
      ct <- 2 
      while (ct <= ds){
        ds.dmg <- ds.dmg + sample(ds.die,1)
        ct <- ct + 1  
      }
      rm (ct)
      dmg <- dmg + ds.dmg 
      rm(ds.dmg)
    }
   
    # double dice damage on crit 
    if (d20==20){dmg <- 2*dmg}
    
    # add flat modifiers 
    dmg <- dmg + str + pb*as.numeric(gwm==1)
    
    # determine topple status (if using maul)
    if (topl==1){
      topl.die <- rep(0,plyr::round_any((1/ptopl),1,ceiling))
      topl.die[1] <- 1
      topple <- sample(topl.die,1)
      rm(topl.die)
    }
  }
  
 # return damage output and topple/crit status
  out <- list("dmg"=dmg,
              "crit"=as.numeric(d20==20),
              "prone"=topple)
  return(out)
}

# Level-01: Paladin-01
{
  # action plan: 
  # 2 combats, cast divine favor on first turn
  # 2 combats, no spellcasting 
  
  # create function evaluating action plan 
  lvl1 <- function(parameters){
    # rename parameters to avoid global/internal conflict 
    params <- parameters 
    
    # combat 1: 
    # turn-1 = BA:divine favor action:attack 
    # turns2-4 = action:attack
    dmg <- 0
    params$divine.favor <- 1
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg # OA
    
    # combat 2 is the same 
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg # OA
    
    # for combat 3 we no longer have divine favor 
    params$divine.favor <- 0 
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg # OA
    
    # same for combat 4
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg
    dmg <- dmg + single.attack(params)$dmg # OA
    
    # compute DPR and return 
    dpr <- dmg/16
    return(dpr)
  }
  
  # set parameters 
  parameters <- list("weapon.die"=c(1:6),
                     "great.weapon.fighting"=0,
                     "great.weapon.master"=0,
                     "topple"=0,
                     "topple.prob"=0,
                     "graze"=1,
                     "strength"=3,
                     "proficiency.bonus"=2,
                     "divine.favor"=0,
                     "divine.smite"=0,
                     "colossus.slayer"=0,
                     "elemental.weapon"=0,
                     "hunters.mark"=0,
                     "sacred.weapon"=0,
                     "guided.strike"=0,
                     "blessed.strike"=0,
                     "enemy.ac"=13,
                     "advantage"=0,
                     "prob.concentrate"=0.8)
  
  # compute expected DPR from lvl1 action plan 
  set.seed(19900320)
  niter <- 10000
  ev <- mean(as.vector(unlist(lapply(as.list(1:niter),function(x) lvl1(parameters)))))
  results.df$EDPR[1] <- ev
  rm(niter,ev,parameters,lvl1)
  gc()
}

# Level-02: Paladin-01, Ranger-01
{
  # action plan: 
  # cast divine favor on turn 1
  # cast hunter's mark on turn 2, and recast it if you lose concentration
  
  # create function evaluating action plan 
  lvl2 <- function(parameters){
    # rename parameters to avoid global/internal conflict 
    params <- parameters 
    
    # spell slots  
    nspells <- 3
    nmarks <- nspells + 2 # x2 free casts of hunter's mark/LR
    
    # set dmg counter 
    dmg <- 0
    
    # combat 1: 
    # randomly assign OA
    oa <- sample(1:4,1)
    # turn-1
    params$divine.favor <- 1
    nspells <- nspells-1
    nmarks <- nmarks-1
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2
    params$hunters.mark <- 1
    nmarks <- nmarks-1
    nspells <- min(nspells,nmarks)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 2
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 3  
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 3  
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # compute DPR and return 
    dpr <- dmg/16
    return(dpr)
  }
  
  # set parameters 
  parameters <- list("weapon.die"=c(1:6),
                     "great.weapon.fighting"=0,
                     "great.weapon.master"=0,
                     "topple"=0,
                     "topple.prob"=0,
                     "graze"=1,
                     "strength"=3,
                     "proficiency.bonus"=2,
                     "divine.favor"=0,
                     "divine.smite"=0,
                     "colossus.slayer"=0,
                     "elemental.weapon"=0,
                     "hunters.mark"=0,
                     "sacred.weapon"=0,
                     "guided.strike"=0,
                     "blessed.strike"=0,
                     "enemy.ac"=13,
                     "advantage"=0,
                     "prob.concentrate"=0.8)
  
  # compute expected DPR from lvl1 action plan 
  set.seed(19900320)
  niter <- 10000
  ev <- mean(as.vector(unlist(lapply(as.list(1:niter),function(x) lvl2(parameters)))))
  results.df$EDPR[2] <- ev
  rm(niter,ev,parameters,lvl2)
  gc()
}

# Level-03: Paladin-01, Ranger-02 
{
  # lvl3 is exactly the same as lvl2, except we add GWF 
  # action plan: 
  # cast divine favor on turn 1
  # cast hunter's mark on turn 2, and recast it if you lose concentration
  
  # create function evaluating action plan 
  lvl3 <- function(parameters){
    # rename parameters to avoid global/internal conflict 
    params <- parameters 
    
    # spell slots  
    nspells <- 3
    nmarks <- nspells + 2 # x2 free casts of hunter's mark/LR
    
    # set dmg counter 
    dmg <- 0
    
    # combat 1: 
    # randomly assign OA
    oa <- sample(1:4,1)
    # turn-1
    params$divine.favor <- 1
    nspells <- nspells-1
    nmarks <- nmarks-1
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2
    params$hunters.mark <- 1
    nmarks <- nmarks-1
    nspells <- min(nspells,nmarks)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 2
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 3  
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 3  
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # compute DPR and return 
    dpr <- dmg/16
    return(dpr)
  }
  
  # set parameters 
  parameters <- list("weapon.die"=c(1:6),
                     "great.weapon.fighting"=1,
                     "great.weapon.master"=0,
                     "topple"=0,
                     "topple.prob"=0,
                     "graze"=1,
                     "strength"=3,
                     "proficiency.bonus"=2,
                     "divine.favor"=0,
                     "divine.smite"=0,
                     "colossus.slayer"=0,
                     "elemental.weapon"=0,
                     "hunters.mark"=0,
                     "sacred.weapon"=0,
                     "guided.strike"=0,
                     "blessed.strike"=0,
                     "enemy.ac"=13,
                     "advantage"=0,
                     "prob.concentrate"=0.8)
  
  # compute expected DPR from lvl1 action plan 
  set.seed(19900320)
  niter <- 10000
  ev <- mean(as.vector(unlist(lapply(as.list(1:niter),function(x) lvl3(parameters)))))
  results.df$EDPR[3] <- ev
  rm(niter,ev,parameters,lvl3)
  gc()
}

# Level-04: Paladin-01, Ranger-03
# NOTE: need to check if we have any remaining spell slots and if so, use them for smites
{
  # lvl-4 we get lvl-2 spell slots and colossus slayer 
  # action plan: 
  # cast divine favor on turn 1
  # cast hunter's mark on turn 2, and recast it if you lose concentration
  # if you have any spell slots left, use them to cast divine smite 
  
  # new version
  lvl4 <- function(parameters){
    # rename parameters to avoid global/internal conflict 
    params <- parameters 
    
    # spell slots 
    spell.slots <- list("lvl1"=4,
                        "lvl2"=2,
                        "free.HM"=2)
    
    # set dmg counter 
    dmg <- 0
    
    # combat 1
    {
      # randomly assign OA
      oa <- sample(1:4,1)
      # turn 1: BA = divine favor + action:attack
      params$divine.favor <- 1
      BA <- 0 
      spell.slots$lvl1 <- spell.slots$lvl1-1
      dmg <- dmg + single.attack(params)$dmg
      if (oa==1){dmg <- dmg + single.attack(params)$dmg}
      BA <- 1
      # turn 2: BA = hunter's mark + action:attack
      params$hunters.mark <- 1
      BA <- 0
      spell.slots$free.HM <- spell.slots$free.HM-1
      dmg <- dmg + single.attack(params)$dmg
      if (oa==2){dmg <- dmg + single.attack(params)$dmg}
      BA <- 1
      # turn 3: concentration check, action:attack, recast HM if needed 
      conc <- as.numeric(runif(1,min=0,max=1)<=params$prob.concentrate)
      if (conc==0){
        if (spell.slots$free.HM>0){spell.slots$free.HM <- spell.slots$free.HM-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1>0){spell.slots$lvl1 <- spell.slots$lvl1-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1==0 & spell.slots$lvl2>0){spell.slots$lvl2 <- spell.slots$lvl2-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1==0 & spell.slots$lvl2==0){params$hunters.mark <- 0}
      }
      dmg <- dmg + single.attack(params)$dmg
      if (oa==3){dmg <- dmg + single.attack(params)$dmg}
      BA <- 1
      # turn 3: concentration check, action:attack, recast HM if needed 
      conc <- as.numeric(runif(1,min=0,max=1)<=params$prob.concentrate)
      if (conc==0){
        if (spell.slots$free.HM>0){spell.slots$free.HM <- spell.slots$free.HM-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1>0){spell.slots$lvl1 <- spell.slots$lvl1-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1==0 & spell.slots$lvl2>0){spell.slots$lvl2 <- spell.slots$lvl2-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1==0 & spell.slots$lvl2==0){params$hunters.mark <- 0}
      }
      dmg <- dmg + single.attack(params)$dmg
      if (oa==4){dmg <- dmg + single.attack(params)$dmg}
      BA <- 1
    }
    
    # combat 2 (STOPPED HERE)
    # need to update attack function to include use of smite on crits
    {
      # randomly assign OA
      oa <- sample(1:4,1)
      # turn 1: BA = divine favor + action:attack
      params$divine.favor <- 1
      if (spell.slots$lvl1>0){spell.slots$lvl1 <- spell.slots$lvl1-1}
      if (spell.slots$lvl1==0 & spell.slots$lvl2>0){spell.slots$lvl2 <- spell.slots$lvl2-1}
      if (spell.slots$lvl1==0 & spell.slots$lvl2==0){params$divine.favor <- 0}
      BA <- 0 
      dmg <- dmg + single.attack(params)$dmg
      if (oa==1){dmg <- dmg + single.attack(params)$dmg}
      BA <- 1
      # turn 2: BA = hunter's mark + action:attack
      params$hunters.mark <- 1 
      if (spell.slots$free.HM>0){spell.slots$free.HM <- spell.slots$free.HM-1}
      if (spell.slots$free.HM==0 & spell.slots$lvl1>0){spell.slots$lvl1 <- spell.slots$lvl1-1}
      if (spell.slots$free.HM==0 & spell.slots$lvl1==0 & spell.slots$lvl2>0){spell.slots$lvl2 <- spell.slots$lvl2-1}
      if (spell.slots$free.HM==0 & spell.slots$lvl1==0 & spell.slots$lvl2==0){params$hunters.mark <- 0}
      BA <- 0
      dmg <- dmg + single.attack(params)$dmg
      if (oa==2){dmg <- dmg + single.attack(params)$dmg}
      BA <- 1
      # turn 3: concentration check, action:attack, recast HM if needed 
      conc <- as.numeric(runif(1,min=0,max=1)<=params$prob.concentrate)
      if (conc==0){
        if (spell.slots$free.HM>0){spell.slots$free.HM <- spell.slots$free.HM-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1>0){spell.slots$lvl1 <- spell.slots$lvl1-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1==0 & spell.slots$lvl2>0){spell.slots$lvl2 <- spell.slots$lvl2-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1==0 & spell.slots$lvl2==0){params$hunters.mark <- 0}
      }
      dmg <- dmg + single.attack(params)$dmg
      if (oa==3){dmg <- dmg + single.attack(params)$dmg}
      BA <- 1
      # turn 3: concentration check, action:attack, recast HM if needed 
      conc <- as.numeric(runif(1,min=0,max=1)<=params$prob.concentrate)
      if (conc==0){
        if (spell.slots$free.HM>0){spell.slots$free.HM <- spell.slots$free.HM-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1>0){spell.slots$lvl1 <- spell.slots$lvl1-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1==0 & spell.slots$lvl2>0){spell.slots$lvl2 <- spell.slots$lvl2-1}
        if (spell.slots$free.HM==0 & spell.slots$lvl1==0 & spell.slots$lvl2==0){params$hunters.mark <- 0}
      }
      dmg <- dmg + single.attack(params)$dmg
      if (oa==4){dmg <- dmg + single.attack(params)$dmg}
      BA <- 1
    }
  }
  
  # create function evaluating action plan 
  # old version
  lvl4 <- function(parameters){
    # rename parameters to avoid global/internal conflict 
    params <- parameters 
    
    # spell slots  
    nspells <- 6
    nmarks <- nspells + 2 # x2 free casts of hunter's mark/LR
    
    # set dmg counter 
    dmg <- 0
    
    # combat 1: 
    # randomly assign OA
    oa <- sample(1:4,1)
    # turn-1
    params$divine.favor <- 1
    nspells <- nspells-1
    nmarks <- nmarks-1
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2
    params$hunters.mark <- 1
    nmarks <- nmarks-1
    nspells <- min(nspells,nmarks)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 2
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 3  
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 3  
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # compute DPR and return 
    dpr <- dmg/16
    return(dpr)
  }
  
  # set parameters 
  parameters <- list("weapon.die"=c(1:6),
                     "great.weapon.fighting"=1,
                     "great.weapon.master"=0,
                     "topple"=0,
                     "topple.prob"=0,
                     "graze"=1,
                     "strength"=3,
                     "proficiency.bonus"=2,
                     "divine.favor"=0,
                     "divine.smite"=0,
                     "colossus.slayer"=1,
                     "elemental.weapon"=0,
                     "hunters.mark"=0,
                     "sacred.weapon"=0,
                     "guided.strike"=0,
                     "blessed.strike"=0,
                     "enemy.ac"=14,
                     "advantage"=0,
                     "prob.concentrate"=0.8)
  
  # compute expected DPR from lvl1 action plan 
  set.seed(19900320)
  niter <- 10000
  ev <- mean(as.vector(unlist(lapply(as.list(1:niter),function(x) lvl4(parameters)))))
  results.df$EDPR[4] <- ev
  rm(niter,ev,parameters,lvl4)
  gc()
}

# Level-05: Paladin-01, Ranger-04
{
  # lvl-5 we get great weapon master 
  # action plan is the same as level 2 and 3,
  # but we use our BA (if avail) when we crit with GWM 
  # cast divine favor on turn 1
  # cast hunter's mark on turn 2, and recast it if you lose concentration
  
  # create function evaluating action plan 
  lvl5 <- function(parameters){
    # rename parameters to avoid global/internal conflict 
    params <- parameters 
    
    # spell slots  
    nspells <- 6
    nmarks <- nspells + 2 # x2 free casts of hunter's mark/LR
    
    # set dmg counter 
    dmg <- 0
    
    # combat 1: 
    # randomly assign OA
    oa <- sample(1:4,1)
    # turn-1
    params$divine.favor <- 1
    nspells <- nspells-1
    nmarks <- nmarks-1
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2
    params$hunters.mark <- 1
    nmarks <- nmarks-1
    nspells <- min(nspells,nmarks)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 2
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 3  
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # combat 3  
    oa <- sample(1:4,1)
    # turn 1
    if (nspells>0){
      params$divine.favor <- 1
      nspells <- nspells-1
      nmarks <- nmarks-1
    }
    if (nspells==0){
      params$divine.favor <- 0
      params$hunters.mark <- 0 
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==1){dmg <- dmg + single.attack(params)$dmg}
    # turn 2 
    if (nmarks>0){
      parameters$hunters.mark <- 1 
      nmarks <- nmarks-1
      nspells <- min(nspells,nmarks)
    }
    dmg <- dmg + single.attack(params)$dmg
    if (oa==2){dmg <- dmg + single.attack(params)$dmg}
    # turn 3
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==3){dmg <- dmg + single.attack(params)$dmg}
    # turn 4 
    nmarks <- max(nmarks - as.numeric(runif(1,min=0,max=1)>params$prob.concentrate),0)
    nspells <- min(nspells,nmarks)
    params$hunters.mark <- as.numeric(nmarks>0)
    dmg <- dmg + single.attack(params)$dmg
    if (oa==4){dmg <- dmg + single.attack(params)$dmg}
    
    # compute DPR and return 
    dpr <- dmg/16
    return(dpr)
  }
  
  # set parameters 
  parameters <- list("weapon.die"=c(1:6),
                     "great.weapon.fighting"=1,
                     "great.weapon.master"=1,
                     "topple"=0,
                     "topple.prob"=0,
                     "graze"=1,
                     "strength"=3,
                     "proficiency.bonus"=2,
                     "divine.favor"=0,
                     "divine.smite"=0,
                     "colossus.slayer"=1,
                     "elemental.weapon"=0,
                     "hunters.mark"=0,
                     "sacred.weapon"=0,
                     "guided.strike"=0,
                     "blessed.strike"=0,
                     "enemy.ac"=15,
                     "advantage"=0,
                     "prob.concentrate"=0.8)
  
  # compute expected DPR from lvl1 action plan 
  set.seed(19900320)
  niter <- 10000
  ev <- mean(as.vector(unlist(lapply(as.list(1:niter),function(x) lvl5(parameters)))))
  results.df$EDPR[5] <- ev
  rm(niter,ev,parameters,lvl4)
  gc()
}




############################# EXTRAS 
# find expected value of 10000 single attacks with given parameters 
set.seed(19900320)
niter <- 10000
ev <- mean(as.vector(unlist(lapply(as.list(1:niter),function(x) single.attack(parameters)$dmg))))




