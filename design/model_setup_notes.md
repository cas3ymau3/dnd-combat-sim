Ok so I want to create an application for simulating the combat performance of my D\&D 5.5e characters. In particular, I'm most interested in computing the average damage per combat round (DPR) dealt to enemies by my character, though there are also other statistics of interest. To compute this, I want to simulate damage in a probabilistic modeling environment many times and then compute the average DPR (as well as other statistics) across all iterations. Below I'm going to describe the different elements of this modeling environment. It may not be perfectly organized though, so I'm going to be relying on you to help my synthesize this and translate it into something implementable. 



Here's the high level structure. The basic interacting elements of the model are called **entities**. There are two types of entities: **objects** and **actors**. Objects are inanimate and don't do anything other than exist and interact with actors. Objects will primarily be used to represent spell or ability-based effects created by another actor (e.g., a spirit guardians emanation, conjure animals, aura of protection, etc). The defining characteristic of an object (in this model) is that it doesn't have HP or game statistics, but does have a **physical presence** -- meaning it has a spatial **footprint** and defined **spatial relationships** with other entities. Actors, on the other hand, are entities that have HP, game statistics, and have some capacity to take actions in combat. Like objects, actors also have a physical presence. So, in the definitional terms of this model framework, actors are defined as having HP, game statistics, a physical presence, and **action economy resources** (defined below). 



There are four types of **actors**: 

1. The Character: a collection of state specific game statistics indicating things like hit points, temp HP, armor class, active weapon/equipped gear, current levels of expendable resources, flags for active statuses/conditions (e.g., concentration), etc. Think of this as a dictionary of values recording and describing all the relevant aspects of our character.
2. The Enemy: a collection of game statistics representing a generic enemy combatant with infinite hit points. This is the target dummy we're going to be attacking.
3. Controlled Allies: E.g., mounts and summoned creatures; we direct how these creatures act in combat and they have their own game statistics 
4. Party Members: An amalgamated representation of the party surrounding the character. The party members actor will be a single entity in the model, but will be structured to represent multiple allies. In combat, our party members won't actually do anything for the purposes of computing average DPR, but the party members actor will have multiple hit point pools that can be the target of enemy attacks/our supportive abilities. We can also use the party members actor to model things like allies as an external source of advantage or healing if we want. For the simulation we'll assume the party members actor contains 3 separate hit point pools/game statistic stat blocks (i.e., that our character is accompanied by 3 other party members).



Note, the character, party members, and the enemy are omnipresent in the model. That is, they exist at the start of the adventuring day and will be present throughout the entire simulation. Objects and controlled allies may be brought into existence (e.g., with a summon spell) and then wink out of existence (e.g., if we lose concentration) at various times throughout the day. In combat, the character, the enemy, and the party members actor have their own turn and initiative. Objects and controlled allies will act/be acted upon during other actor's turns (for example, moved on the character's turn).  



There are four types of **action economy resources**, where these are based on the core rules of play for D\&D 5.5e. All actors have access to at least one of these action economy resources, which they are able to use during combat. Objects don't have action economy resources. 

1. Actions
2. Bonus Actions
3. Reactions
4. Movement



Events: There are only three types of **event** that occur during this model at specific times throughout the day - **short resting**, **combat** and **out-of-combat actions**. Each model run is meant to represent a **standard adventuring day**, defined as follows: 

* Assuming 8hr for a long rest, the standard day of adventuring is 16hrs long, measured in minutes = 960 minutes. 
* Each day begins at period t=1 (minute 1) with the completion of a long rest (recover all HP and limited resources that recover on a LR, reset THP, decrease exhaustion, etc.) 
* Four combats occur each day. The first combat starts at a randomly selected time on the interval t in \[1,239]. The second combat starts at a randomly selected time on the interval t in \[240,479], the third combat starts at a randomly selected time on the interval t in \[480,719], and the last combat starts at a randomly selected time on the interval t in \[720,960]. Note, this framing makes it possible (though unlikely) for continuing effects with longer duration (e.g., spells with duration of 10m or 1hr) to last across two combats, but impossible to have more than 2 combats within a span of 4 hrs (240 minutes). This seems reasonable. The start time for each combat is randomly selected at the beginning of each day.  
* In terms of day time, each combat lasts exactly 1m. Within that minute, each combat is comprised of 4 rounds combat rounds (16 total combat rounds per day) 
* We assume 1 short rest per day by default. Short rests take 1hr (60m) to complete. The selection of the timing of combats during the adventuring day defines three intervals of time during which the short rest can potentially occur. Interval 1 = after the end of combat 1 and before the start of combat 2. Interval 2 = after the end of combat 2 and before the start of combat 3. Interval 3 = after the end of combat 3 and before the start of combat 4. The selection rule is as follows. If Interval 2 is >=60 minutes in duration/length, we assume the SR occurs during interval 2. If not, randomly select (with equal probability) whether the SR will occur in Interval 1 or Interval 3. Note that given how we select the timing of combats, if interval 2 is <60m, then both interval 1 and interval 3 will be >60m. Given the interval selection, assume the SR occurs at the first minute within the interval, and ends 60m later. 
* Out of combat actions are events that occur when the character actor uses resources outside of combat and when not short resting. For example, casting an out of combat spell (like magic weapon, or mage armor). The time and manner in which these resources are used will be specified by the character's **daily plan** which is described in further detail below. For ther purposes of understanding the modeling of events throughout the day -- suffice it to say that the daily plan will specify a set of conditions which, in combination with the timing of combats and short rests during the day, will translate into a specific event time during which the character's out-of-combat actiosn will take place. 
* Finally, note this representation of the day means we are technically including an implicit representation of a long rest as another event that occurs during the day. So I guess we could consider a long rest a model event. But it has no bearing on the mechanically interacting parts of the model. And is just a result of the implicit structure of timing in the model environment, so I didn't consider it as an explicit event. 



Combat initiation, progression, and timing

* Combat begins with rolling initiative. Roll initiative for our character, our party members (as a single entity), and the enemy separately to determine turn order. Assume controlled allies and objects created by the character act on the character's turn and interact with other entities on those entity's turns (e.g., deal damage to the enemy on their turn).  
* The first actor's turn starts after initiative is rolled and the spatial relationships between entities on the battlefield are resolved (see below). This also initiates the first round. An actor's turn ends when they've used all the action economy resources (action, bonus action, movement, reaction) available to them on their turn. Note - skipping/doing nothing with a resource will also count as using it. 
* A round ends when the last actor in the initiative order has finished their turn. The next round begins when the first actor in the initiative order starts their turn. 
* Combat ends after the last actor in the initiative order finishes their turn on round-04. 



Spatial relationships between entities

* This isn't going to be an explicitly spatial model. Instead we're going to try and drastically simplify things. 
* During combat, we're going to model each entity's relationship in space to each other entity as a 0/1 binary state variable.
* A spatial relationship state of 1 will mean that an entity is *near* another entity. In game mechanics terms, one entity being near another will mean they are `in melee' with that entity
* A spatial relationship state of 0 will mean that an entity is *far* from another entity. In game mechanics terms, one entity being far from another will mean they are `at range' with that enemy. 
* By definition, entities are always near themselves. Some entities might also have fixed spatial relationships with one another by default, based on what they are meant to represent. For example, a controlled ally with the mount tag will always be near the character. As will an object representing a spell emanation where the emanation originates from the character. 
* Given this, with N entities in a given combat, all spatial relationships can be described by a symmetrical boolean NxN matrix with 1's on the diagonal
* When defining and updating this spatial relationship matrix, we are going to treat nearness as transitive. That is, if Actor A is near Actor B, and Actor B is near Object 1, then Actor A is also near Object 1. So basically we're assuming that entities that are near each other are just in a big clump and all near each other all at once. This is a simplification of real D\&D play, but makes intuitive sense and keeps things simple. 
* When combat starts and initiative is rolled, but before the first actor's first turn, we randomly generate a symmetrical boolean NxN matrix with 1's on the diagonal and which satisfies the transitive property of nearness. We then make sure this matrix satisfies all fixed spatial relationship conditions inherited from the entities involved in combat (for example the character being near their mount, or the character's spell emanation being near them). This represents the spatial relationships between entities at the beginning of combat. After this spatial relationship matrix is properly initialized, combat progresses to the first actor in the initiative order's first turn. 
* This matrix is then updated dynamically on each actor's turn based on a which of a predefined set of movement options (see below) they take. The matrix can also expand or contract in dimension as entities (objects/controlled allies) appear or disappear during combat. At end of each turn, we'll also make sure any default fixed spatial relationships are satisfied. 
* For controlled allies or objects that do not have a fixed/default spatial relationship to the character (like a mount or emanation): If the were created ouf of combat and are present when initiative is rolled, they are incorporated into the initial start-of-combat spatial relationship matrix like any other entity. However if they are created as part of an action during combat, we can specify their spatial relationship to a target (for example, the enemy) as part of the action that creates them, and then, given this initial condition, infer the relationship between the new entity and all other entities present in the combat based on the transitive property of nearness and the spatial relationship between pre-existing entities at the time the new entity is created.  
* At the end of combat, the spatial relationship matrix is discarded/deleted



Movement during combat

* We won't model movement explicitly. Instead, building off our treatment of spatial relationships, we'll try to do something equally simple. 
* Actors who have access to the movement action economy resource can do the following: (1) choose an entity with whom their current spatial relationship is far and move near to that target (and all other nearby targets), (2) move out of melee and simultaneously change their relationship to all other actors to far (i.e., move away from everyone else), or (3) don't move. 
* To allow for the modeling of builds that depend on speed reduction effects or the trapping enemies/buffing of allies in areas of effect, we have to add a bit more complexity. First, actors can only take movement options (1) and (2) if they have movement speed >=5ft. This will basically allow us to represent things like grappled and/or restrained that set an entity's movement speed to zero. Second, when attempting to move away from a nearby entity (movement option 2), we have to account for the entity's spatial footprint relative to the moving actor's speed. Recall that an entity's physical presence is defined by its footprint, which will now interact actors' game statistics (speed) to affect the result of their movement action economy resources. 
* To elaborate, the basic picture we should have in mind here is a spell-based emanation effect. The spell creates an object (e.g., a spirit guardians emanation) that is near to the character (by default), near to all actors in melee with the character (by the transitive property of nearness) and far from all actors not in melee with the character. By definition, the object has a spatial footprint. In the case of spirit guardians the footprint of the emanation is 15ft. In this example, assume the enemy is near to the spell effect object when it is created (i.e, we are standing next to the enemy when we cast spirit guardians). Then, on the enemy's turn, in order for them to use their movement action economy resource to take movement action (2) and change their relationship with the spirit guardians object from near to far (and thus escape it's damaging effects), they have to have movement speed greater than or equal to the object's footprint (in spirit guardian's case, it would actually be twice the object's footprint because it creates difficult terrain, but that's for later).
* To generalize and formalize this, we'll just say that all entities have a base footprint of 5ft unless otherwise specified (as would be the case for a spell effect with an emanation). In order to move away from an entity (movement option 2), the entity must have movement speed greater than or equal to the footprint of all entities that it is currently near to. And in order to up to/towards an enemy, an entity must have movement speed >= 5ft. This obviously ignores a lot of real spatial dynamics in D\&D play. But it's a simplification that will make the model tractable. 
* So, at the beginning of each actor's turn, we determine which of the three movement options are possible given the current state of spatial relationships and the characteristics of actors on the field. The actor then chooses which movement option to take, given the available options that are possible and the preferences around movement dictated in their actor description or daily plan. 
* QUESTION: HOW TO TREAT MOVEABLE OBJECTS, FORCED MOVEMENT, AND MOUNTS? 
* CONCERN: I'm not sure this framework will work well. For one thing. It doesn't allow you to move away from one entity without moving away from all others. For example, an enemy might not be able to move out of our spirit guardians emanation, but would still be able to move away from our character. This could be materially important given the nature of character spells and abilities. Second, I'm not sure how well controlled allies (especially mounts) and objects will function within this type of setup. Seems like the whole spatial simplification thing could be a bit clunky. But maybe that's ok. 



Enemy behavior in combat

* The enemy has access to the following action economy resources in combat: action, movement. By default on their turn, the enemy takes their action and doesn't move. So we won't model any enemy bonus actions or reactions (at least not explicitly, see below). We also won't be modeling any statuses or conditions imposed on our character or allies by enemy actions.
* An enemy can take one of two generic actions on their turn. The first generic enemy action is the **enemy attack** action, which is meant to represent any monster ability that deals damage via an attack roll (such as an attack or multi-attack). The second generic action is the **enemy spell** action, which generically represents any monster ability that deals damage by forcing a saving throw. The total damage potential of each of these two abilities will be equal, and will scale with enemy challenge rating (CR) based on secondary sources that document average damage per round at different CR levels. For the enemy attack option, the total damage potential will be divided into a number of individual attacks that scales with CR (single attack at low levels, multi-attacks at higher levels). For the enemy spell option, the specific saving throw targeted will be randomly selected, based on a probability distribution (also varying with CR) reflecting the prevalence of abilities/spells targeting each type of save from the core rulebooks (e.g., 2024 PHB, Monster Manual), and we'll assume that the enemy spell option deals half damage on a successful save. We'll assume a fixed probability that the enemy uses the enemy attack versus enemy spell action on each turn, where this probability reflects the observed prevalence of attack roll vs. saving throw based abilities in monster stat blocks in the core rulebooks (weighted towards attack rolls). We'll assume both of these enemy actions have infinite range, and so can always target our character or any of our independent/controlled allies. 
* Targeting probability: By default, we'll assume the enemy randomly targets one actor (either us or our allies) on their turn. So we're not modeling AOE effects. Actor traits/characteristics can affect the probability of being targeted, both statically and dynamically. For example, characters with the `melee' tag/trait should have a higher probability of being targeted than `ranged' characters. And characters with the `invisible' condition on the enemy's turn should have a reduced probability of being targeted. If the enemy is grappled by our character, this should increase the probability of being targeted. We'll also assume that when using an ability that requires an attack roll, the enemy prioritizes attacking targets at advantage, then targets where they have a straight roll, and prefers not to attack targets at disadvantage if possible. We'll model this preference statically, and only when considering abilities that require attack rolls, versus those that force saving throws.
* To model enemy reactions, we'll assume the only thing an enemy does with their reaction is make an attack of opportunity if and only if our character provokes one from them on their (the character's) turn. If triggered, the attack of opportunity will be modeled based on the damage/statistics of the enemy attack action, but with only a single attack roll/instance of damage (i.e., no multi-attack). Whether or not this triggers on the character's turn will be modeled with a status flag (provoked enemy OoA) that is set/updated based on actions/movement taken on our character's turn). So, as stated above, the enemy does not have a `reaction' action economy resource. 
* If the enemy is subjected to the prone condition, we assume it uses half its movement speed at the start of its turn to stand up
* If the enemy is subjected to the grappled condition, we assume there is a fixed probability that it uses its action to attempt to break the grapple. If it doesn't try to break the grapple it uses its action to do enemy attack or enemy spell
* If the enemy is subjected to any other condition (e.g., restrained by a net) where they can use an action to remove the condition, assume that they do immediately on their turn. 
* Similarly, for damaging or debuffing effects created by spells, abilities, or controlled allies that occupy a specific area, we assume that the enemy attempts to move out of the area of effect immediately at the start of their turn if possible (and uses the dash action if necessary). 



Enemy game statistics

* Static enemy game statistics scale with CR/character level according to a pre-specified input parameter table
* Static enemy statistics include: AC, bonus to ability checks and saving throws for each ability score/skill, spell save DC, bonus to attack rolls, total damage per enemy spell/enemy attack action, number of attacks in enemy attack action, probability of targeting each type of saving throw with enemy spell action
* Dynamic enemy statistics include: targeting probability, status flags, size, speed
* Size and speed are modeled randomly based on the observed distribution of creature size in the 2024 Monster Manual



Controlled allies' behavior in combat

* Controlled allies have the following action economy resources: action, bonus action, reaction, movement
* Unless otherwise specified by our character, controlled allies take the dodge action, skip their bonus action, and don't move
* Unless otherwise specified by our character, controlled allies only use their rection to make an opportunity attack if one is triggered. To model triggering, we assume the following. If the creature is a mount then the enemy triggers an attack of opportunity from it whenever it would trigger an attack of opportunity from our character. If the controlled ally is not a mount (e.g., a summon) an attack of opportunity triggers if the enemy moves from near to far (from the controlled entity) on their turn.  



Party members' game statistics 

* Party members are modeled as a single collective entity with X (3) different infinite hit point pools. Statuses (such as advantage or AC boosts) apply to all entities simultaneously. Healing and THP generation are applied to each sub-entity separately. 
* For saving throws, the party members' saving throw bonus will just equal the character's proficiency bonus.
* For attack/spell attack bonus, we assume it's equal to PB+3
* Static party member statistics scale with CR/character level according to a pre-specified input parameter table
* Static party member statistics include: AC, bonus saving throws for each ability score, spell save DC, bonus to attack rolls
* Dynamic party member statistics include: status flags, size, speed



Party members' behavior in combat

* Party members have the action and movement action economy resources. 
* By default party members do nothing in combat. We aren't interested in modeling full party dynamics/interactions. The main reason we have them in the framework is to provide potential targets for enemy actions, so that we can model our character's survivability more accurately. 
* However, we might also be interested in modeling/evaluating supportive character abilities that affect allies, such as healing/THP generation, boosts to ally AC or saving throws, or boosts to ally damage (e.g, via advantage generation or debuffs to enemy saving throws)
* To accommodate this, we do want our framework to allow party members to take generic actions similar to generic enemy actions. 
* For the purposes of being targeted by enemy actions our party members represent a number of distinct entities (multiple different targets). For the purposes of their actions during combat/on their turn, we will just model them as one collective entity for simplicity. 
* While party members don't move by default, they will move to avoid damaging effects (like spell effects) if possible. 



Character game statistics, resources/abilities, and progression

* Character game statistics are given as a function of character level accoring to their **build plan**, which is a basic input to the model
* Character level affects a variety of things in the character stat block, including HP, equipment/gear (which can affect AC), proficiency bonus, ability scores, saving throws, skill proficiencies/bonuses, attack and spell attack roll bonuses, flat bonuses to hit and damage with attacks, etc. 
* However the main thing that dictates character progression is the accumulation of character abilities and resources (described below)



There are two types of character abilities: active and passive 

* active character abilities require some sort of action economy resource to use -- such as an action, bonus action, or reaction in combat or the expenditure of a resource out of combat. Things like spells, rage, action surge, channel divinity, etc., are examples of active character abilities. 
* passive character abilities apply directly to the characters stat block or passively modify an existing action economy resource or ability. For example, the fast movement ability of a monk passively increases the character's movement speed. The tough feat passively increases a character's HP. And a rogue's sneak attack ability passively increases the damage of weapon attacks if they meet certain conditions. 
* Both active and passive character abilities have a duration -- either measured in minutes or based on some other condition (like until your next attack roll, or until the enemy's next saving throw). Some are permanent (infinite duration). 
* Both active and passive character abilities can require character resources to use. They may also be costless (free to use/always on). Others may allow for a variety of resource inputs (for example, a spell that can be cast with a lvl-01 or any higher lvl spell slot). Still others may require other conditions for use. For example, a 
* In essence, character abilities are like skills for Claude code. They are predefined packages that enable new character actions, or modify existing character abilities. 
* At a baseline, every character has access to the following active abilities: attack, dodge, disengage, unarmed strike (damage), unarmed strike (shove), unarmed strike (grapple)  
* Our model environment should contain a living/ever-expanding dictionary of defined character abilities that we can reference when we start defining the build plan and daily plan for a particular character



Character resources 

* Character resources are inputs to character abilities that require resources to use. By nature, resources are limited. Spell slots, charges, and uses are all examples of resources. 
* The character acquires resources as they level up as a function of the character abilities to which they have access. This progression is described in their build plan. 
* Every resource is defined by (i) a number of uses, and (ii) the way in which the resource recovers. For example, a lvl-01 spell caster has 2 lvl-01 spell slots and these recover on a long rest. A lvl-01 warlock has 1 lvl-01 pact magic slot, and this recovers on a short rest. A lvl-02 cleric has 2 uses of channel divinity, and regains one charge on a short rest. 
* Character resources are tracked throughout the adventuring day, and their use throughout the day is specified in the **daily plan**
* Note that action economy resources are also resources (as defined here). Each action economy resource has a single use (one action per turn/round) and recovers each turn/round. 



Character build plan 

* This is a table that describes character progression from lvl-01 to lvl-20. It details what happens to the character at each level, including how their game statistics and equipment change, and what new abilities and resources they gain access to at each level. 



Character daily plan

* A character's daily plan describes how the character behaves throughout the adventuring day. This includes conditional logic dictating how they behave in every round of every combat, and rules and conditional logics that explicitly dictate how the character uses their abilities and resources 
* The character has a daily plan for every character level from lvl-01 to lvl-20, though it's possible for the plan to be identical at multiple levels. The full set of 20 daily plans (1 for each level) is another basic input to the model. 



Character behavior in combat

* On their turn, the character actor has access to the following action economy resources: action, bonus action, movement.
* Controlled allies or objects created by the character, and certain character abilities or status effects, can also gain access to additional action economy resources. For example, a character can direct a summoned creature to take an action on their turn, the action surge ability gives a character a second action resource, as does the haste spell (status: hasted)
* The character also gets 1 reaction per round, which they can use in one of the following ways: (i) on another actor's turn to take an action in response to a specified trigger (e.g., provoking an opportunity attack, taking damage, etc.), (ii) on their own turn to prepare a specified action and trigger condition (e.g., take attack action when enemy leaves your reach).



Statuses and status effects  

* Actors can be affected by statuses in combat 
* Mechanically statuses are tracked by boolean flags that indicate whether or not they are active 
* Statuses can be beneficial or detrimental -- for example the "bless" status conveys a +1d4 on attack rolls and saving throws while the "poisoned" status imposes disadvantage on attack rolls and ability checks 
* For our model, many statuses will be drawn directly from the core 2024 rules -- for example, grappled, restrained, incapacitated, stunned, etc. 
* However, many other statuses will be defined to reflect specific character abilities -- for example "hexblades curse" will be used to indicate whether or not a target has been cursed by a hexblade warlock's hexblade's curse ability. 
* Statuses, like abilities, will be defined in a separate dictionary that is provided as a separate input to the model. 
* Concentration will also be a key status = initiated by the use of an ability that requires it; and tracked during combat. 



Outputs 

* The key output we want to track is the character's damage output per combat round, but there are many other things we also want to track. These may include: 
* the amount of damage taken by the character
* the amount of damage reduced by the character
* the amount of HP recovered by the character 
* the number of attack rolls made by the character, the number of hits made by the character, the number of critical hits landed, the percentage of attacks that result in hits, the percentage of attacks that result in critical hits, the number of attacks made with advantage, the percentage of attacks made with advantage 
* the number of saving throws forced by the character, by saving throw type, the number of times the enemy failed a saving throw forced by the character (again by saving throw type) and the percentage of saving throws failed (by type) 
* the number of all limited character resources used per day, and per combat 
* the share of turns the character is concentrating; the number of times the character's concentration is broken 
* the share of turns the character, party members, other specified entities (e.g., summons), or the enemy are subject to specified status conditions (e.g., blessed, grappled, etc.) 
* the average damage per use, on hit, and on crit of each damaging ability used by the character
* the HP/damage taken by party members or created allies  
* if specified, the success rate of attacks/spells made by party members or created allies



