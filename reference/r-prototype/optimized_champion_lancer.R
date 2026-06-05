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
 # STR = 15 (+2) = 17
 # DEX = 13
 # CON = 15 (+1) = 16
 # INT = 8 
 # WIS = 12
 # CHA = 8

# Species: Human 
 # Origin feats: lucky, savage attacker  

# Weapon: lance = 1d10 piercing (topple); heavy, reach, two-handed

# Build:
 # lvl-1: lucky, savage attacker 
 # lvl-1: great weapon fighting (gwf)
 # lvl-4: polearm master (STR=18)
 # lvl-6: great weapon master (STR=19)
 # lvl-8: piercer (STR=20) 
 # lvl-12: charger (DEX=14) 
 # lvl-14: heavy armor master (CON=17) 
 # lvl-16: speedy (CON=18)
 # lvl-19: epic boon of combat prowess (STR=21)


# ASSUMPTIONS 
 # (1)
 # GWF applies to all rerolled damage dice, including on rerolls 
 # from savage attacker and piercer. GWF applies to the extra crit
 # die added by the piercer feat's eanhanced critical subfeature.
 # GWF also applies to BA attack from PAM. 
 # (2)
 # With a single attack, you are always able to use your reroll features on crits
 # With two attacks, you are able to use your reroll featurs on crits 50% of the time 
 # With three attacks, you are able to use your reroll features on crits 33% of the time 
 # (3)
 # You use all luck points to give yourself advantage on lance attacks 
 # (4) 
 # You successful prone targets 50% of the time, and enemies stand up on their turn
 # (5)
 # 4 combats per day, 4 rounds per combat, 1 short rest per day 
 # (6) 
 # Once you have GWM, you always use hew BA attack when you score a critical hit 
 # (7) 
 # You are able to make an attack of opportunity (OA) in 25% of combat rounds, and in 33% of 
 # of combat rounds once you have PAM 

# Attack rules 
  # reroll 7's and lower with savage attacker 
  # reroll 5's and lower with piercer 
  # on crit: 
    # use both features on a single die if one die is >5
    # use 1 feature on each roll if they are both <5

   
# Create functions to compute expected value of attack(s)
weapon.dmg <- function(weapon.die,gwf,savage.att,piercer,puncture,crit){
  # weapon.die = weapon damage die outcomes 
  # gwf = great weapon fighting (y/n)
  # savage.att = use savage attacker reroll (y/n)
  # piercer = do you have piercer feat (y/n)
  # puncture = use piercer reroll (y/n)
  # crit = critical hit (y/n)
  if(piercer==0){puncture<-0} 
  if (gwf==1){weapon.die[weapon.die<3] <- 3}
  dmg <- (1/length(weapon.die))*sum(weapon.die)
  if (crit==0){
  if (savage.att==1 & puncture==0){
    grid <- expand.grid(weapon.die,weapon.die)
    colnames(grid) <- c("die1","die2")
    grid$val <- as.vector(apply(grid[,c("die1","die2")],1,function(x) max(x)))
    exval <- ((1/length(weapon.die))^2)*sum(as.vector(unlist(grid$val)))
    thresh.val <- max(which(weapon.die<exval))
    dmg <- (thresh.val/length(weapon.die))*exval + sum((1/length(weapon.die))*weapon.die[weapon.die>thresh.val])
    rm(grid,exval,thresh.val)
  }
  if (savage.att==0 & puncture==1){
    thresh.val <- max(which(weapon.die<dmg))
    dmg <- (thresh.val/length(weapon.die))*dmg + sum((1/length(weapon.die))*weapon.die[weapon.die>thresh.val])
    rm(thresh.val)
  }
  if (savage.att==1 & puncture==1){
    # use savage att first
    # if result is still lower than piercer thresh.val, use piercer 
    grid <- expand.grid(weapon.die,weapon.die)
    colnames(grid) <- c("die1","die2")
    grid$val <- as.vector(apply(grid[,c("die1","die2")],1,function(x) max(x)))
    exval <- ((1/length(weapon.die))^2)*sum(as.vector(unlist(grid$val)))
    thresh.val1 <- max(which(weapon.die<exval))
    thresh.val2 <- max(which(weapon.die<dmg))
    rows1 <- which(grid$val>thresh.val2)
    prob1 <- length(rows1)/nrow(grid)
    prob2 <- length(which(grid$val<=thresh.val2))/nrow(grid)
    dmg <- sum((1/length(weapon.die))*weapon.die[weapon.die>thresh.val1]) + # EV if original roll is higher than savage.att threshold
           prob1*((1/length(weapon.die))^2)*sum(as.vector(unlist(grid$val[rows1]))) + # EV if savage attacker roll is higher than piercer threshold
           prob2*((thresh.val2/length(weapon.die))*dmg + sum((1/length(weapon.die))*weapon.die[weapon.die>thresh.val2])) # EV if you reroll again with piercer
    rm(grid,exval,thresh.val1,thresh.val2,rows1,prob1,prob2)
  }
  }
  if (crit==1){
    if (piercer==0 & puncture==0 & savage.att==0){dmg <- 2*dmg}
    if (piercer==0 & puncture==0 & savage.att==1){
      grid <- expand.grid(weapon.die,weapon.die)
      colnames(grid) <- c("die1","die2")
      grid$val <- as.vector(apply(grid[,c("die1","die2")],1,function(x) max(x)))
      exval <- ((1/length(weapon.die))^2)*sum(as.vector(unlist(grid$val)))
      thresh.val <- max(which(weapon.die<exval))
      dmg <- 2*((thresh.val/length(weapon.die))*exval + sum((1/length(weapon.die))*weapon.die[weapon.die>thresh.val]))
      rm(grid,exval,thresh.val)
    }
    if (piercer==1 & puncture==0 & savage.att==0){
      # in this case, we simply add 1d10 to the expected damage with no reroll
      dmg <- 2*(dmg+(1/length(weapon.die))*sum(weapon.die))
    }
    if (piercer==1 & puncture==1 & savage.att==0){
      # In this case, we roll 2d10, then pick the lowest one to reroll 
      # with our piercer reroll. 
      grid <- expand.grid(weapon.die,weapon.die)
      colnames(grid) <- c("die1","die2")
      grid$min <- as.vector(unlist(apply(grid,1,function(x) min(x))))
      grid$max <- as.vector(unlist(apply(grid[,c("die1","die2")],1,function(x) max(x))))
      grid$reroll <- grid$min
      thresh.val <- max(which(weapon.die<dmg))
      grid$reroll[which(grid$reroll<=thresh.val)] <- (1/length(weapon.die))*sum(weapon.die)
      grid$dmg <- grid$max+grid$reroll
      dmg <- 2*((1/length(weapon.die))^2)*sum(as.vector(unlist(grid$dmg)))
      rm(grid,thresh.val)
    }
    if (piercer==1 & puncture==0 & savage.att==1){
      # in this case you would use the savage attacker reroll on your lowest damage die
      grid <- expand.grid(weapon.die,weapon.die)
      colnames(grid) <- c("die1","die2")
      grid$max <- as.vector(unlist(apply(grid,1,function(x) max(x))))
      grid$min <- as.vector(unlist(apply(grid[,c("die1","die2")],1,function(x) min(x))))
      grid$reroll <- grid$min
      ev.reroll <- (1/length(weapon.die))^2*sum(grid$max)
      thresh.val <- max(which(weapon.die<ev.reroll))
      rows <- which(grid$reroll<=thresh.val)
      grid$reroll[rows] <- ev.reroll
      grid$dmg <- grid$max + grid$reroll
      dmg <- 2*(1/length(weapon.die))^2*sum(grid$dmg)
      rm(grid,ev.reroll,thresh.val,rows)
    }
    if (piercer==1 & puncture==1 & savage.att==1){
      # Now you have a choice of using both savage attacker + 
      # piercer reroll on a single damage die, or using one on one die
      # and the other on the second die. 
      
      # The possibilities are: 
      # (1) both rolls are > 7 --> don't reroll at all 
      # (2) one roll is > 7 and one roll is <= 7 --> use both features on low roll
      # (3) both rolls are <=7
        # (3a) one/both rolls = 6 --> use both features on low roll 
        # (3b) both rolls are <=5 --> use one feature on each roll 
      
      # If you use one reroll for each die, then you get: 
      # 5.8 EV on one die (expected value of single reroll with piercer)
      # 7.2 EV on the other die (expected value of double reroll with savage attacker)
      # so you get a total EV of: 5.8 + 7.2 = 13
      
      # If you use both features on a single die, you replace one die value with 7.65 (see calc below)
      # so even if you roll a 5 on one die, you will still avg 12.65, 
      # which is lower than what you get if you use one feature on each roll. 
      {
      # grid2 <- expand.grid(weapon.die,weapon.die)
      # colnames(grid2) <- c("die1","die2")
      # grid2$val <- as.vector(apply(grid2[,c("die1","die2")],1,function(x) max(x)))
      # grid2$reroll <- grid2$val
      # grid2$reroll[which(grid2$reroll<=thresh.val)] <- (1/length(weapon.die))*sum(weapon.die)
      # ev2 <- ((1/length(weapon.die))^2)*sum(as.vector(unlist(grid2$reroll)))
      # rm(grid2)
      }
      
      # setup grid of possible outcomes 
      grid <- expand.grid(weapon.die,weapon.die)
      colnames(grid) <- c("die1","die2")
      grid$max <- as.vector(apply(grid[,c("die1","die2")],1,function(x) max(x)))
      grid$min <- as.vector(apply(grid[,c("die1","die2")],1,function(x) min(x)))
      savatt.ev <- ((1/length(weapon.die))^2)*sum(as.vector(unlist(grid$max)))
      thresh.val1 <- max(which(weapon.die<savatt.ev))
      thresh.val2 <- max(which(weapon.die<dmg))
      grid$reroll.max <- grid$max
      grid$reroll.min <- grid$min
      
      # expected value of using both features on single roll 
      grid2 <- expand.grid(weapon.die,weapon.die)
      colnames(grid2) <- c("die1","die2")
      grid2$val <- as.vector(apply(grid2[,c("die1","die2")],1,function(x) max(x)))
      grid2$reroll <- grid2$val
      grid2$reroll[which(grid2$reroll<=thresh.val2)] <- (1/length(weapon.die))*sum(weapon.die)
      ev2 <- ((1/length(weapon.die))^2)*sum(as.vector(unlist(grid2$reroll)))
      rm(grid2)
      
      # (2) one roll is > 7 and one roll is <= 7 --> use both features on low roll
      rows <- which(grid$reroll.max > thresh.val1 & grid$reroll.min<=thresh.val1)
      grid$reroll.min[rows] <- ev2
      rm(rows)
      
      # (3a) one/both rolls = 6 --> use both features on low roll 
      rows <- which(grid$reroll.max <= thresh.val1 & grid$reroll.max > thresh.val2)
      grid$reroll.min[rows] <- ev2
      rm(rows)
      
      # (3b) both rolls are <=5 --> use one feature on each roll
      rows <- which(grid$reroll.max <= thresh.val2 & grid$reroll.min <= thresh.val2)
      grid$reroll.min[rows] <- (1/length(weapon.die))*sum(weapon.die)
      grid$reroll.max[rows] <- ev2
      rm(rows)
      
      # compute aggregate expected value 
      grid$dmg <- grid$reroll.min + grid$reroll.max 
      dmg <- 2*((1/length(weapon.die))^2)*sum(as.vector(unlist(grid$dmg)))
      
      # clean up 
      rm(grid,savatt.ev,thresh.val1,thresh.val2,ev2)
    }
  }
  return(dmg)
}
crit.prob <- function(improved,superior,adv){
  prob <- 1/20
  if (improved==1){prob <- prob+1/20}
  if (superior==1){prob <- prob+1/20}
  if (adv==1){
    grid <- expand.grid(c(1:20),c(1:20))
    colnames(grid) <- c("die1","die2")
    grid$max <- as.vector(unlist(apply(grid,1,function(x) max(x))))
    grid$crit <- 0
    grid$crit[which(grid$max==20)] <- 1
    if (improved==1){grid$crit[which(grid$max==19)] <- 1}
    if (superior==1){grid$crit[which(grid$max==18)] <- 1}
    prob <- ((1/20)^2)*sum(as.vector(unlist(grid$crit)))
  }
  return(prob)
}
hit.prob <- function(pb,str,adv,ac){
  thresh <- ac-(str+pb) # what you need to roll to hit
  if (adv==0){prob <- 1-(thresh/20)}
  if (adv==1){
    grid <- expand.grid(c(1:20),c(1:20))
    colnames(grid) <- c("die1","die2")
    grid <- grid[order(grid$die1,grid$die2),]
    grid$max <- as.vector(unlist(apply(grid,1,function(x) max(x))))
    grid$hit <- as.numeric(grid$max>=thresh)
    prob <- (1/(20)^2)*sum(as.vector(unlist(grid$hit)))
    rm(grid)
  }
  return(prob)
}
single.attack <- function(parameters){
  # parameters:
  # wd = weapon die 
  wd <- parameters$wd
  # gwf = great weapon fighting 
  gwf <- parameters$gwf
  # gwm = great weapon master
  gwm <- parameters$gwm
  # sa = savage attack reroll (y/n)
  sa <- parameters$sa
  # prc = piercer feature
  prc <- parameters$prc
  # pun = puncture reroll 
  pun <- parameters$pun
  # lvl = character level: determines pb, class features
  lvl <- parameters$lvl
  # str = strength score 
  str <- parameters$str
  # ac = enemy ac 
  ac <- parameters$ac
  # adv = do you have advantage on the attack
  adv <- parameters$adv
  
  # get pb and imp/sup class features from character level 
  {
  if (lvl<3){
    pb <- 2
    imp <- 0 
    sup <- 0
  }
  if (lvl>=3 & lvl<5){
    pb <- 2 
    imp <- 1
    sup <- 0
  }
  if (lvl>=5 & lvl<9){
    pb <- 3
    imp <- 1
    sup <- 0 
  }
  if (lvl==9){
    pb <- 4
    imp <- 1 
    sup <- 0 
  }
  if (lvl>9 & lvl<13){
    pb <- 4
    imp <- 1
    sup <- 1
  }
  if (lvl>=13 & lvl<17){
    pb <- 5
    imp <- 1 
    sup <- 1
  }
  if (lvl>=17){
    pb <- 6
    imp <- 1
    sup <- 1
  }
  }
  
  # compute expected value of single attack
  ev <-  hit.prob(pb,str,adv,ac)*(crit.prob(imp,sup,adv)*weapon.dmg(wd,gwf,sa,prc,pun,1) + 
                                  (1-crit.prob(imp,sup,adv))*weapon.dmg(wd,gwf,sa,prc,pun,0) + 
                                  str + as.numeric(gwm==1)*pb)
  # return output 
  return(ev)
}
pam.attack1 <- function(parameters)


# Create dataframe to store results 
results.df <- data.frame("lvl"=1:20,
                         "PB"=c(rep(2,4),rep(3,4),rep(4,4),rep(5,4),rep(6,4)),
                         "feat.ASI"=c("Savage Attacker, GWF","Action Surge","Improved Crit, Remarkable Athlete","PAM (STR=18)","Extra Attack, PB=3",
                                      "GWM (STR=19)","Defense","Piercer (STR=20)","Indomitable, PB=4","Heroic Warrior","Extra Attack (x3)",
                                      "Charger (DEX=14)","Studied Attacks, PB=5","Heavy Armor Master (CON=17)","Superior Crit","Speedy (CON=18)",
                                      "Action Surge (x2), Indomitable (x3), PB=6","Survivor","Epic Boon of Combat Prowess","Extra Attack (x4)"),
                         "enemy.AC"=c(rep(13,3),14,rep(15,3),rep(16,2),rep(17,3),rep(18,4),rep(19,2),rep(20,2)))
results.df$EDPR <- NA 

# Level-1 
{
  # we make 1 attack per round, with gwf and savage attacker
  # we have 2 luck points plus 1 heroic advantage (from human::resourceful)
  att.params1 <- list("wd"=c(1:10),
                      "gwf"=1,
                      "gwm"=0,
                      "sa"=1,
                      "prc"=0,
                      "pun"=0,
                      "lvl"=1,
                      "str"=3,
                      "ac"=13,
                      "adv"=0)
  att.params2 <- att.params1
  att.params2$adv <- 1
  # 13 rounds + 4 OAs not at advantage, 3 attacks at advantage
  edpr <- (17*single.attack(att.params1) + 3*single.attack(att.params2))/16 
  results.df$EDPR[1] <- round(edpr,2)
  rm(att.params1,att.params2,edpr)
}

# Level-2
{
  # we get action surge, allowing us to make one additional attack on a turn
  # assume that we use action surge after making an enemy prone to gain advantage 
  att.params1 <- list("wd"=c(1:10),
                      "gwf"=1,
                      "gwm"=0,
                      "sa"=1,
                      "prc"=0,
                      "pun"=0,
                      "lvl"=2,
                      "str"=3,
                      "ac"=13,
                      "adv"=0)
  att.params2 <- att.params1
  att.params2$adv <- 1
  # 13 rounds + 4 OAs not at advantage, 4 attacks at advantage (one from Action Surge)
  edpr <- (17*single.attack(att.params1) + 4*single.attack(att.params2))/16 
  results.df$EDPR[2] <- round(edpr,2)
  rm(att.params1,att.params2,edpr)
}

# Level-3
{
  # we get champion subclass and improved critical feature 
  # otherwise math stays the same 
  att.params1 <- list("wd"=c(1:10),
                      "gwf"=1,
                      "gwm"=0,
                      "sa"=1,
                      "prc"=0,
                      "pun"=0,
                      "lvl"=3,
                      "str"=3,
                      "ac"=13,
                      "adv"=0)
  att.params2 <- att.params1
  att.params2$adv <- 1
  # 13 rounds + 4 OAs not at advantage, 4 attacks at advantage (one from Action Surge)
  edpr <- (17*single.attack(att.params1) + 4*single.attack(att.params2))/16
  results.df$EDPR[3] <- round(edpr,2)
  rm(att.params1,att.params2,edpr)
}

# Level-4
{
  # we get polearm master (PAM) and we boost our STR to 18 (+4)
  # assume that we use our BA to make the PAM on our turn each round 
  # assume we are able to make OAs/reactive strikes on 1/3 (rounded down) of rounds (so 5) 
  # assume we prone our enemy before making our BA attack 50% of the time 
  
  # lance attacks 
  att.params1 <- list("wd"=c(1:10),
                      "gwf"=1,
                      "gwm"=0,
                      "sa"=1,
                      "prc"=0,
                      "pun"=0,
                      "lvl"=4,
                      "str"=4,
                      "ac"=14,
                      "adv"=0)
  att.params2 <- att.params1
  att.params2$adv <- 1
  
  # PAM bonus action attacks (no savage attacker)
  att.params3 <- att.params1 
  att.params3$wd <- c(1:4)
  att.params3$sa <- 0 
  att.params4 <- att.params3
  att.params4$adv <- 1 
  att.params4$sa <- 0 
  
  # Now we can only use savage attacker rerolls once per turn. We preferentially use 
  # it to reroll damage die on our lance attacks, but if we haven't used it, then we 
  # should use it to reroll our BA PAM attack. So then we know that we should reroll
  # the lance attack on a 7 or lower. So that means, 70% of the time, we'll use savage
  # attacker on our lance attack, and 30% of the time, we'll use it on our BA polearm
  # master attack. The EV of a lance attack that rolls 8+ is (1/3)*(8+9+10) = 9 dmg
  
  edpr.noadv <- 0.7*(single.attack(att.params1) + 0.5*(single.attack(att.params3) + single.attack(att.params4))) + 
                0.3*()
  
  
  
  # 13 rounds + 4 OAs not at advantage, 4 attacks at advantage (one from Action Surge)
  edpr <- (17*single.attack(att.params1) + 4*single.attack(att.params2))/16
  results.df$EDPR[3] <- round(edpr,2)
  rm(att.params1,att.params2,edpr)
  
}




############################# EXTRAS 
wd <- c(3,3,3,4,5,6)
grid <- expand.grid(wd,wd)
colnames(grid) <- c("die1","die2")
grid$sum <- as.vector(apply(grid[,c("die1","die2")],1,function(x) sum(x)))
mean(grid$sum)
grid2 <- expand.grid(as.vector(grid$sum),as.vector(grid$sum))
colnames(grid2) <- c("sum1","sum2")
grid2$max <- as.vector(apply(grid2[,c("sum1","sum2")],1,function(x) max(x)))
mean(grid2$max)


exval <- ((1/length(weapon.die))^2)*sum(as.vector(unlist(grid$val)))
thresh.val <- max(which(weapon.die<exval))
dmg <- (thresh.val/length(weapon.die))*exval + sum((1/length(weapon.die))*weapon.die[weapon.die>thresh.val])
rm(grid,exval,thresh.val)





