
# value of sharpened mind assuming you hit with psychic blade (no sneak attack)
{
fn1 <- function(psidie.roll){
  # roll damage on psychic blade 
  roll <- sample(1:6,1)
  # replace damage with psidie.roll if higher 
  roll <- max(roll,psidie.roll)
  return(roll)
}

# iterations
n.iter <- 10000 

# if we get a psionic die roll of 1
psidie <- 1
set.seed(1234)
mean1 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn1(psidie.roll=psidie))))) # 3.5  

# if we get a psionic die roll of 2
psidie <- 2
set.seed(1234)
mean2 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn1(psidie.roll=psidie))))) # 3.67 

# if we get a psionic die roll of 3
psidie <- 3
set.seed(1234)
mean3 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn1(psidie.roll=psidie))))) # 4.0 

# if we get a psionic die roll of 4
psidie <- 4
set.seed(1234)
mean4 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn1(psidie.roll=psidie))))) # 4.5 

# if we get a psionic die roll of 5
psidie <- 5
set.seed(1234)
mean5 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn1(psidie.roll=psidie))))) # 5.17

# if we get a psionic die roll of 6
psidie <- 6
set.seed(1234)
mean6 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn1(psidie.roll=psidie))))) # 6.00

# Average value for d6 psionic die 
overall.mean6 <- mean(c(mean1,mean2,mean3,mean4,mean5,mean6)) # 4.47

# Average value for d8 psionic die 
overall.mean8 <- mean(c(mean1,mean2,mean3,mean4,mean5,mean6,7,8)) # 5.23

# Average value for d8 psionic die with guaranteeed 4+  
overall.mean8a <- mean(c(mean4,mean4,mean4,mean4,mean5,mean6,7,8)) # 5.52

}
# Summary:
  # With a d6 psionic die (psion-02), sharpened mind increases the average damage of your d6 psychic blade from 3.50 to 4.47 (+0.97)
  # With a d8 psionic die (psion-05), sharpened mind increases the average damage of your d6 psychic blade from 3.50 to 5.23 (+1.73)
  # With a d8 psionic die and psionic surge (psion-07), the average damage of a d6 psychic blade increases from 3.50 to 5.52 (+2.02)
  # Assuming base crit multiplier of 7.5% (some attacks at advantage)
    # psion-02 increases damage from 3.76 to 4.81 (+1.05, 28%)
    # psion-05 increases damage from 3.76 to 5.62 (+1.86, 49%)
    # psion-07 increases damage from 3.76 to 5.93 (+2.17, 58%)

# value of sharpened mind assuming you hit with psychic blade and deal 2d6 sneak attack damage (also psychic)
{
  fn2 <- function(psidie.roll){
    # roll damage on psychic blade (die 1)
    roll1 <- sample(1:6,1)
    # roll sneak attack damage (die 2)
    roll2 <- sample(1:6,1)
    # roll sneak attack damage (die 3)
    roll3 <- sample(1:6,1)
    # replace lowest roll with psidie.roll if higher 
    rolls <- c(roll1,roll2,roll3)
    ind <- min(which(rolls==min(rolls)))
    rolls[ind] <- max(rolls[ind],psidie.roll)
    dmg <- sum(rolls)
    return(dmg)
  }
  
  # iterations
  n.iter <- 10000 
  
  # if we get a psionic die roll of 1
  psidie <- 1
  set.seed(1234)
  mean1 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn2(psidie.roll=psidie))))) # 10.5   
  
  # if we get a psionic die roll of 2
  psidie <- 2
  set.seed(1234)
  mean2 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn2(psidie.roll=psidie))))) # 10.93
  
  # if we get a psionic die roll of 3
  psidie <- 3
  set.seed(1234)
  mean3 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn2(psidie.roll=psidie))))) # 11.63 
  
  # if we get a psionic die roll of 4
  psidie <- 4
  set.seed(1234)
  mean4 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn2(psidie.roll=psidie))))) # 12.51
  
  # if we get a psionic die roll of 5
  psidie <- 5
  set.seed(1234)
  mean5 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn2(psidie.roll=psidie))))) # 13.47
  
  # if we get a psionic die roll of 6
  psidie <- 6
  set.seed(1234)
  mean6 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn2(psidie.roll=psidie))))) # 14.47
  
  # if we get a psionic die roll of 7
  psidie <- 7
  set.seed(1234)
  mean7 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn2(psidie.roll=psidie))))) # 15.47
  
  # if we get a psionic die roll of 8
  psidie <- 8
  set.seed(1234)
  mean8 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn2(psidie.roll=psidie))))) # 16.47
  
  # Average value for d6 psionic die 
  overall.mean6 <- mean(c(mean1,mean2,mean3,mean4,mean5,mean6)) # 12.25
  
  # Average value for d8 psionic die 
  overall.mean8 <- mean(c(mean1,mean2,mean3,mean4,mean5,mean6,mean7,mean8)) # 13.18
  
  # Average value for d8 psionic die with guaranteeed 4+  
  overall.mean8a <- mean(c(mean4,mean4,mean4,mean4,mean5,mean6,mean7,mean8)) # 13.74
}
# Summary:
  # With a d6 psionic die (psion-02), sharpened mind increases the average damage of psychic blade + sneak attack from 10.50 to 12.25 (+1.75)
  # With a d8 psionic die (psion-05), sharpened mind increases the average damage of psychic blade + sneak attack from 10.50 to 13.18 (+2.68)
  # With a d8 psionic die and psionic surge (psion-07), the average damage of psychic blade + sneak att increases from 10.50 to 13.74 (+3.24)
  # Assuming base crit multiplier of 7.5% (some attacks at advantage)
    # psion-02 increases damage from 11.29 to 13.17 (+1.88, 17%)
    # psion-05 increases damage from 11.29 to 14.17 (+2.88, 26%)
    # psion-07 increases damage from 11.29 to 14.77 (+3.48, 31%) --> almost exactly equal to 1d6 extra sneak attack dmg 

# value of sharpened mind assuming you hit with psychic blade, deal 2d6 sneak attack damage, and deal 1d4 psychic dmg with BA blade (all psychic)
{
  fn3 <- function(psidie.roll){
    # roll damage on psychic blade (die 1)
    roll1 <- sample(1:6,1)
    # roll sneak attack damage (die 2)
    roll2 <- sample(1:6,1)
    # roll sneak attack damage (die 3)
    roll3 <- sample(1:6,1)
    # roll BA psychic blade damage (die 4)
    roll4 <- sample(1:4,1)
    # replace lowest roll with psidie.roll if higher 
    rolls <- c(roll1,roll2,roll3,roll4)
    ind <- min(which(rolls==min(rolls)))
    rolls[ind] <- max(rolls[ind],psidie.roll)
    dmg <- sum(rolls)
    return(dmg)
  }
  
  # iterations
  n.iter <- 10000 
  
  # if we get a psionic die roll of 1
  psidie <- 1
  set.seed(1234)
  mean1 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn3(psidie.roll=psidie))))) # 13.00  
  
  # if we get a psionic die roll of 2
  psidie <- 2
  set.seed(1234)
  mean2 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn3(psidie.roll=psidie))))) # 13.59
  
  # if we get a psionic die roll of 3
  psidie <- 3
  set.seed(1234)
  mean3 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn3(psidie.roll=psidie))))) # 14.44 
  
  # if we get a psionic die roll of 4
  psidie <- 4
  set.seed(1234)
  mean4 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn3(psidie.roll=psidie))))) # 15.40
  
  # if we get a psionic die roll of 5
  psidie <- 5
  set.seed(1234)
  mean5 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn3(psidie.roll=psidie))))) # 16.40
  
  # if we get a psionic die roll of 6
  psidie <- 6
  set.seed(1234)
  mean6 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn3(psidie.roll=psidie))))) # 17.40
  
  # if we get a psionic die roll of 7
  psidie <- 7
  set.seed(1234)
  mean7 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn3(psidie.roll=psidie))))) # 18.40
  
  # if we get a psionic die roll of 8
  psidie <- 8
  set.seed(1234)
  mean8 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn3(psidie.roll=psidie))))) # 19.40
  
  # Average value for d6 psionic die 
  overall.mean6 <- mean(c(mean1,mean2,mean3,mean4,mean5,mean6)) # 15.04
  
  # Average value for d8 psionic die 
  overall.mean8 <- mean(c(mean1,mean2,mean3,mean4,mean5,mean6,mean7,mean8)) # 16.00
  
  # Average value for d8 psionic die with guaranteeed 4+  
  overall.mean8a <- mean(c(mean4,mean4,mean4,mean4,mean5,mean6,mean7,mean8)) # 16.65
}
# Summary:
  # With a d6 psionic die (psion-02), sharpened mind increases the avg dmg of psychic blade + sneak attack + BA::psychic blade from 13.00 to 15.00 (+2)
  # With a d8 psionic die (psion-05), sharpened mind increases the avg dmg of psychic blade + sneak attack + BA::psychic blade from 13.00 to 16.00 (+3)
  # With a d8 psionic die and psionic surge (psion-07), the avg dmg of psychic blade + sneak att + BA::psychic blade increases from 13.00 to 16.65 (+3.65)
  # Assuming base crit multiplier of 7.5% (some attacks at advantage)
    # psion-02 increases damage from 13.98 to 16.13 (+2.15, 15%)
    # psion-05 increases damage from 13.98 to 17.20 (+3.22, 23%)
    # psion-07 increases damage from 13.98 to 17.90 (+3.92, 28%) 

# value of sharpened mind assuming you hit with psychic blade, deal 2d6 sneak attack damage, deal 1d4 psychic damage with BA blade, and have savage attacker 
{
  fn4 <- function(psidie.roll){
    # roll damage on psychic blade (die 1)
    roll1a <- sample(1:6,1)
    roll1b <- sample(1:6,1) # roll second die from savage attacker 
    roll1 <- max(roll1a,roll1b)
    # roll sneak attack damage (die 2)
    roll2 <- sample(1:6,1)
    # roll sneak attack damage (die 3)
    roll3 <- sample(1:6,1)
    # roll BA psychic blade damage (die 4)
    roll4 <- sample(1:4,1)
    # replace lowest roll with psidie.roll if higher 
    rolls <- c(roll1,roll2,roll3,roll4)
    ind <- min(which(rolls==min(rolls)))
    rolls[ind] <- max(rolls[ind],psidie.roll)
    dmg <- sum(rolls)
    return(dmg)
  }
  
  # iterations
  n.iter <- 10000 
  
  # if we get a psionic die roll of 1
  psidie <- 1
  set.seed(1234)
  mean1 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn4(psidie.roll=psidie))))) # 13.97  
  
  # if we get a psionic die roll of 2
  psidie <- 2
  set.seed(1234)
  mean2 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn4(psidie.roll=psidie))))) # 14.47
  
  # if we get a psionic die roll of 3
  psidie <- 3
  set.seed(1234)
  mean3 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn4(psidie.roll=psidie))))) # 15.27 
  
  # if we get a psionic die roll of 4
  psidie <- 4
  set.seed(1234)
  mean4 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn4(psidie.roll=psidie))))) # 16.23
  
  # if we get a psionic die roll of 5
  psidie <- 5
  set.seed(1234)
  mean5 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn4(psidie.roll=psidie))))) # 17.23
  
  # if we get a psionic die roll of 6
  psidie <- 6
  set.seed(1234)
  mean6 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn4(psidie.roll=psidie))))) # 18.23
  
  # if we get a psionic die roll of 7
  psidie <- 7
  set.seed(1234)
  mean7 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn4(psidie.roll=psidie))))) # 19.23
  
  # if we get a psionic die roll of 8
  psidie <- 8
  set.seed(1234)
  mean8 <- mean(as.vector(unlist(lapply(as.list(1:n.iter),function(x) fn4(psidie.roll=psidie))))) # 20.23
  
  # Average value for d6 psionic die 
  overall.mean6 <- mean(c(mean1,mean2,mean3,mean4,mean5,mean6)) # 15.90
  
  # Average value for d8 psionic die 
  overall.mean8 <- mean(c(mean1,mean2,mean3,mean4,mean5,mean6,mean7,mean8)) # 16.85
  
  # Average value for d8 psionic die with guaranteeed 4+  
  overall.mean8a <- mean(c(mean4,mean4,mean4,mean4,mean5,mean6,mean7,mean8)) # 17.48
}
  # With a d6 psionic die (psion-02), sharpened mind + savage attacker increases the avg dmg from 13.00 to 15.89 (+2.89)
  # With a d8 psionic die (psion-05), sharpened mind + savage attacker increases the avg dmg from 13.00 to 16.85 (+3.85)
  # With a d8 psionic die and psionic surge (psion-07), sharpened mind + savage attacker increases the avg dmg from 13.00 to 17.48 (+4.5)
  # Assuming base crit multiplier of 7.5% (some attacks at advantage)
    # psion-02 increases damage from 13.98 to 17.08 (+3.1, 22%)
    # psion-05 increases damage from 13.98 to 18.11 (+4.13, 30%)
    # psion-07 increases damage from 13.98 to 18.79 (+4.81, 34%) 
