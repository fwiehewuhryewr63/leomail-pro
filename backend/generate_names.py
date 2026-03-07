"""
Generate large name packs (5000+ unique combos) for ALL target GEOs.
Uses real census/statistical name frequency data.
Run: python generate_names.py
"""
import random
import os
from extra_countries import (
    UK_FIRST_MALE, UK_FIRST_FEMALE, UK_LAST,
    RU_FIRST_MALE, RU_FIRST_FEMALE, RU_LAST,
    EG_FIRST_MALE, EG_FIRST_FEMALE, EG_LAST,
    NG_FIRST_MALE, NG_FIRST_FEMALE, NG_LAST,
    ZA_FIRST_MALE, ZA_FIRST_FEMALE, ZA_LAST,
    AR_FIRST_MALE_ARAB, AR_FIRST_FEMALE_ARAB, AR_LAST_ARAB,
    IN_FIRST_MALE, IN_FIRST_FEMALE, IN_LAST,
    PH_FIRST_MALE, PH_FIRST_FEMALE, PH_LAST,
    TR_FIRST_MALE, TR_FIRST_FEMALE, TR_LAST,
)

# ─────────────────────────────────────────────────────────
# SHARED SPANISH LATAM SURNAMES (common across all countries)
# ─────────────────────────────────────────────────────────
LATAM_COMMON_LAST = [
    "Garcia","Rodriguez","Martinez","Lopez","Gonzalez","Hernandez","Perez","Sanchez","Ramirez","Torres",
    "Flores","Rivera","Gomez","Diaz","Reyes","Morales","Jimenez","Ruiz","Ortiz","Castillo",
    "Vargas","Romero","Mendoza","Cruz","Herrera","Medina","Aguilar","Guerrero","Santos","Delgado",
    "Vega","Rios","Contreras","Castro","Fuentes","Navarro","Ramos","Silva","Rojas","Escobar",
    "Cortes","Campos","Valencia","Leon","Montoya","Paredes","Miranda","Serrano","Figueroa","Molina",
    "Mora","Bravo","Salazar","Acosta","Espinoza","Luna","Cervantes","Dominguez","Cardenas","Ibarra",
    "Pacheco","Camacho","Cabrera","Trujillo","Rangel","Salinas","Bautista","Ponce","Duarte","Chavez",
    "Aguirre","Leal","Parra","Estrada","Quintero","Tovar","Zamora","Sandoval","Mejia","Montes",
    "Pena","Guzman","Ochoa","Maldonado","Avila","Palacios","Velazquez","Fernandez","Soto","Nunez",
]

# ─── COMMON SPANISH MALE FIRST NAMES ───
SPANISH_MALE_COMMON = [
    "Carlos","Miguel","Jose","Juan","Luis","Pedro","Jorge","Antonio","Francisco","Manuel",
    "Ricardo","Fernando","Alejandro","Rafael","Roberto","Daniel","Eduardo","Sergio","Alberto","Mario",
    "Andres","Diego","Enrique","Raul","Javier","Arturo","Oscar","Victor","Hector","Pablo",
    "Hugo","Marco","Cesar","Ruben","Gerardo","Ernesto","Alfredo","Gustavo","Armando","Ramon",
    "Felipe","Salvador","Ignacio","Mauricio","Adrian","Gabriel","Julian","Guillermo","Rodrigo","Tomas",
    "Ivan","Emilio","Alonso","Sebastian","Nicolas","Gonzalo","Mateo","Santiago","Martin","Leonardo",
    "Esteban","Joaquin","Cristian","Benjamin","Agustin","Bruno","Matias","Emiliano","Alan","Axel",
]

# ─── COMMON SPANISH FEMALE FIRST NAMES ───
SPANISH_FEMALE_COMMON = [
    "Maria","Ana","Patricia","Gabriela","Laura","Rosa","Carmen","Claudia","Elena","Isabel",
    "Lucia","Veronica","Daniela","Adriana","Monica","Alejandra","Teresa","Carolina","Fernanda","Leticia",
    "Andrea","Mariana","Paulina","Valentina","Sofia","Camila","Ximena","Natalia","Diana","Paola",
    "Regina","Renata","Valeria","Victoria","Lorena","Alicia","Cristina","Silvia","Julieta","Josefina",
    "Beatriz","Sandra","Marisol","Catalina","Florencia","Guadalupe","Mercedes","Esperanza","Gloria","Irma",
    "Susana","Yolanda","Alma","Blanca","Cecilia","Paloma","Jimena","Dulce","Karla","Karina",
    "Martha","Olivia","Jessica","Fabiola","Miriam","Emilia","Antonia","Sara","Clara","Rebeca",
]

# ─────────────────────────────────────────────────────────
# PER-COUNTRY ADDITIONS (unique names + unique surnames)
# ─────────────────────────────────────────────────────────

# ─── COLOMBIA ───
CO_EXTRA_MALE = ["Santiago","Mateo","Camilo","Esteban","Fabian","Gonzalo","Stiven","Yeison","Duvan","Ferney",
                  "Nestor","Arley","Jeferson","Robinson","Leider","Maicol","Yeferson","Didier","Fredy","Elkin"]
CO_EXTRA_FEMALE = ["Valentina","Isabella","Manuela","Salome","Luisa","Lina","Katherine","Yuliana","Viviana","Lizeth",
                    "Johanna","Leidy","Yenny","Yaneth","Ingrid","Kelly","Erika","Aura","Esmeralda","Eliana"]
CO_EXTRA_LAST = ["Ospina","Bernal","Munoz","Cifuentes","Caicedo","Velasquez","Marin","Hurtado","Bedoya","Henao",
                  "Zapata","Quintana","Arango","Cardona","Correa","Gil","Arias","Jaramillo","Osorio","Cano",
                  "Gaviria","Giraldo","Rendon","Uribe","Echeverri","Betancur","Botero","Posada","Restrepo","Velez"]

# ─── ARGENTINA ───
AR_EXTRA_MALE = ["Lionel","Facundo","Thiago","Santino","Luciano","Damian","Lautaro","Nahuel","Bautista","Braian",
                  "Maximo","Tobias","Valentino","Gael","Ciro","Benicio","Lisandro","Ramiro","Leandro","Franco"]
AR_EXTRA_FEMALE = ["Sol","Morena","Martina","Lara","Pilar","Milagros","Candela","Rocio","Agustina","Abril",
                    "Ludmila","Micaela","Aylen","Julieta","Celeste","Bianca","Aldana","Florencia","Jazmin","Oriana"]
AR_EXTRA_LAST = ["Fernandez","Alvarez","Romero","Sosa","Pereyra","Gimenez","Gutierrez","Diaz","Benitez","Acosta",
                  "Suarez","Medina","Ledesma","Mansilla","Aguero","Bustos","Ferreyra","Villalba","Coria","Peralta",
                  "Blanco","Paz","Arias","Cabral","Barrionuevo","Lucero","Ojeda","Coronel","Godoy","Rolon"]

# ─── PERU ───
PE_EXTRA_MALE = ["Jhon","Brayan","Cristhian","Pool","Iker","Gianmarco","Piero","Renato","Alonso","Yordy",
                  "Beto","Claudio","Cesar","Wilfredo","Percy","Clever","Nilton","Renzo","Edison","Jhonatan"]
PE_EXTRA_FEMALE = ["Milagros","Fiorella","Pierina","Kiara","Xiomara","Yuliana","Gianella","Mayte","Lucero","Flor",
                    "Briggitte","Deysi","Yessica","Yanina","Rosario","Lizbeth","Luz","Soledad","Ingrid","Shirley"]
PE_EXTRA_LAST = ["Quispe","Mamani","Huaman","Condori","Flores","Ccama","Apaza","Choque","Hancco","Ticona",
                  "Cusihuaman","Gutierrez","Ramos","Huanca","Vilca","Soto","Lazo","Calle","Zeballos","Arce",
                  "Benavides","Cespedes","Cordova","Meza","Vasquez","Tapia","Alarcon","Caceres","Carbajal","Valverde"]

# ─── VENEZUELA ───
VE_EXTRA_MALE = ["Yonathan","Deivis","Wuilker","Yohandry","Maikel","Jhonny","Wilmer","Deivi","Enderson","Yorman",
                  "Yeferson","Brayan","Jeison","Kevin","Wilmar","Franklyn","Jhonier","Leandro","Reinaldo","Eliezer"]
VE_EXTRA_FEMALE = ["Yuleisy","Darianny","Yoselin","Keilyn","Mileidy","Yurley","Karinely","Oriana","Greisy","Maribel",
                    "Yineth","Dayana","Yulianny","Angely","Migdalia","Lisbeth","Marielys","Nairobys","Zuleica","Leandra"]
VE_EXTRA_LAST = ["Gonzalez","Rodriguez","Perez","Hernandez","Garcia","Martinez","Lopez","Diaz","Ramirez","Sanchez",
                  "Torres","Moreno","Mendez","Suarez","Pineda","Rincon","Marquez","Lara","Colmenares","Padrino",
                  "Duran","Blanco","Rivero","Barrios","Zambrano","Chacon","Carrillo","Salazar","Paredes","Linares"]

# ─── CHILE ───
CL_EXTRA_MALE = ["Bastian","Maximiliano","Vicente","Agustin","Joaquin","Gaspar","Renato","Cristobal","Ignacio","Alonso",
                  "Tomas","Matias","Benjamin","Lucas","Martin","Facundo","Damian","Luciano","Emiliano","Franco"]
CL_EXTRA_FEMALE = ["Isidora","Agustina","Antonia","Martina","Catalina","Josefa","Trinidad","Maite","Monserrat","Colomba",
                    "Thiare","Constanza","Javiera","Francisca","Belen","Ignacia","Emilia","Amanda","Paz","Valentina"]
CL_EXTRA_LAST = ["Munoz","Sepulveda","Araya","Vergara","Tapia","Fuentes","Soto","Henriquez","Aravena","Espinoza",
                  "Cornejo","Bravo","Jara","Villalobos","Contreras","Figueroa","Lagos","Valenzuela","Carrasco","Alvarez",
                  "Bustos","Pizarro","Donoso","Garrido","Orellana","Caceres","Moya","Farias","Retamal","Alarcon"]

# ─── ECUADOR ───
EC_EXTRA_MALE = ["Jefferson","Jhon","Stalin","Lenin","Erick","Bryan","Kevin","Ariel","Josue","Omar",
                  "Cristhian","Kleber","Geovanny","Willian","Fabricio","Ronny","Elvis","Holger","Bayron","Galo"]
EC_EXTRA_FEMALE = ["Kerly","Evelyn","Maribel","Yessenia","Gissela","Nathaly","Mishel","Dayana","Solange","Ligia",
                    "Narcisa","Aida","Digna","Germania","Zoila","Bertha","Celinda","Emperatriz","Nelly","Rocio"]
EC_EXTRA_LAST = ["Zambrano","Alvarado","Cevallos","Intriago","Moreira","Loor","Macias","Vera","Pin","Mero",
                  "Briones","Chila","Cornejo","Espinales","Tubay","Toala","Cantos","Mendez","Quimi","Bailon",
                  "Centeno","Andrade","Barreiro","Pincay","Reyes","Veliz","Navarrete","Solorzano","Galarza","Chica"]

# ─── GUATEMALA ───
GT_EXTRA_MALE = ["Josue","Mynor","Brayan","Erick","Estuardo","Byron","Kelvin","Osman","Fredy","Elder",
                  "Nery","Selvin","Rudy","Gilberto","Waldemar","Anibal","Erwin","Mynor","Saul","Obdulio"]
GT_EXTRA_FEMALE = ["Lesly","Kimberly","Wendy","Heidy","Sindy","Yenifer","Dulce","Evelyn","Jackeline","Madelyn",
                    "Astrid","Ingrid","Brenda","Paola","Zully","Floridalma","Aura","Telma","Vilma","Catarina"]
GT_EXTRA_LAST = ["Perez","Lopez","Gonzalez","Garcia","Martinez","Rodriguez","Hernandez","Morales","Ramirez","Castillo",
                  "Reyes","Alvarez","De Leon","Mendez","Barrios","Velasquez","Juarez","Santos","Cifuentes","Cano",
                  "Ajcuc","Cuc","Ixchop","Xol","Tum","Choc","Pop","Tax","Caal","Tzoc"]

# ─── DOMINICAN REPUBLIC ───
DO_EXTRA_MALE = ["Starlin","Wander","Yonatan","Kelvin","Joan","Elvis","Franklyn","Yeison","Hansel","Arismendy",
                  "Dariel","Melvin","Yunior","Bladimir","Adalberto","Aneury","Cristhian","Diomedes","Ezequiel","Fausto"]
DO_EXTRA_FEMALE = ["Yokasta","Yanelis","Genesis","Wendy","Miguelina","Yudelka","Franchesca","Massiel","Kenia","Yamilet",
                    "Raisa","Julissa","Fiordaliza","Altagracia","Dariana","Leanny","Rosanny","Yokaira","Ambar","Griselda"]
DO_EXTRA_LAST = ["Rodriguez","Perez","Martinez","Garcia","Gonzalez","Sanchez","Hernandez","Diaz","Lopez","Ramirez",
                  "Reyes","De La Cruz","Mejia","Marte","Rosario","Paulino","Pena","Batista","Santos","Almonte",
                  "Bautista","Duran","Encarnacion","Familia","Guzman","Jimenez","Lora","Mercedes","Nova","Ozuna"]

# ─── HONDURAS ───
HN_EXTRA_MALE = ["Josue","Bayron","Erick","Osman","Brayan","Nery","Denis","Selvin","Elder","Wilmer",
                  "Alexander","Edgardo","Marlon","Danilo","Rolando","Reynaldo","Santos","Nixon","Rigoberto","Lenin"]
HN_EXTRA_FEMALE = ["Lesly","Wendy","Kimberly","Sindy","Yenifer","Heidy","Jackeline","Madelyn","Yessica","Xiomara",
                    "Angie","Karla","Yulissa","Belkis","Nery","Tania","Suyapa","Meylin","Scarleth","Oneyda"]
HN_EXTRA_LAST = ["Lopez","Hernandez","Martinez","Garcia","Rodriguez","Perez","Gonzalez","Reyes","Sanchez","Ramirez",
                  "Flores","Cruz","Diaz","Mejia","Ortiz","Bustillo","Funes","Zelaya","Pineda","Matamoros",
                  "Villanueva","Canales","Euceda","Lagos","Maradiaga","Murillo","Ordonez","Portillo","Suazo","Turcios"]

# ─── PARAGUAY ───
PY_EXTRA_MALE = ["Derlis","Nestor","Arnaldo","Blas","Cayo","Edgar","Fabian","Julio","Osvaldo","Sinforiano",
                  "Cristhian","Alcides","Eladio","Ever","Guido","Hernan","Lorenzo","Milciades","Porfirio","Silvio"]
PY_EXTRA_FEMALE = ["Zunilda","Ramona","Gladys","Liz","Rossana","Dahiana","Cynthia","Perla","Jazmin","Magali",
                    "Larissa","Fatima","Griselda","Noelia","Dolly","Mirtha","Norma","Estela","Petrona","Dominga"]
PY_EXTRA_LAST = ["Gonzalez","Rodriguez","Martinez","Lopez","Garcia","Fernandez","Benitez","Gimenez","Ortiz","Villalba",
                  "Duarte","Caceres","Acosta","Sanchez","Ramirez","Rojas","Bogado","Espinola","Fleitas","Gauto",
                  "Insaurralde","Jara","Lezcano","Meza","Noguera","Ojeda","Paredes","Rios","Sosa","Torres"]

# ─── EL SALVADOR ───
SV_EXTRA_MALE = ["Josue","Bryan","Kevin","Erick","Osman","Denis","Marvin","Darwin","Wilber","Gerson",
                  "Nelson","Santos","Fredy","Rene","Mauricio","Saul","Boris","Dagoberto","Elmer","Bladimir"]
SV_EXTRA_FEMALE = ["Karina","Yesenia","Evelyn","Wendy","Roxana","Fatima","Delmy","Xiomara","Reina","Yaneth",
                    "Deysi","Blanca","Morena","Dinora","Sonia","Arely","Bessy","Glenda","Idalia","Lissette"]
SV_EXTRA_LAST = ["Hernandez","Martinez","Lopez","Gonzalez","Garcia","Rodriguez","Perez","Sanchez","Ramirez","Flores",
                  "Rivera","Cruz","Diaz","Reyes","Morales","Ramos","Portillo","Mejia","Orellana","Alvarado",
                  "Bonilla","Avalos","Castaneda","Escobar","Franco","Grande","Henriquez","Iraheta","Jovel","Lazo"]

# ─── NICARAGUA ───
NI_EXTRA_MALE = ["Josue","Bayron","Erick","Osman","Denis","Marvin","Darwin","Ervin","Bismarck","Noel",
                  "Lenin","Bayardo","Crisanto","Edgard","Harvin","Jairo","Marlon","Norvin","Otoniel","Scarleth"]
NI_EXTRA_FEMALE = ["Reyna","Scarleth","Yolanda","Xiomara","Fatima","Auxiliadora","Idania","Petrona","Socorro","Azucena",
                    "Darling","Francela","Indiana","Johana","Karla","Luz","Meyling","Nohemi","Olga","Perla"]
NI_EXTRA_LAST = ["Lopez","Garcia","Martinez","Hernandez","Gonzalez","Rodriguez","Perez","Sanchez","Ramirez","Diaz",
                  "Flores","Morales","Cruz","Torres","Reyes","Gutierrez","Ruiz","Ortiz","Vargas","Romero",
                  "Aleman","Blandon","Carrion","Davila","Espinales","Fonseca","Galeano","Herrera","Jarquin","Lacayo"]

# ─── COSTA RICA ───
CR_EXTRA_MALE = ["Josue","Esteban","Fabian","Andrey","Kendall","Keylor","Bryan","Jason","Erick","Randall",
                  "Royner","Deyver","Yeltsin","Jeison","Ariel","Gerardo","Minor","Mynor","Olman","Dagoberto"]
CR_EXTRA_FEMALE = ["Daniela","Karol","Tatiana","Hazel","Kimberly","Yerlin","Yesenia","Monserrat","Naomy","Rebeca",
                    "Priscilla","Silvia","Wendy","Gloriana","Viviana","Ivannia","Mariela","Natasha","Pamela","Raquel"]
CR_EXTRA_LAST = ["Rodriguez","Jimenez","Mora","Hernandez","Gonzalez","Vargas","Chacon","Ramirez","Sanchez","Rojas",
                  "Salazar","Arias","Solis","Valverde","Brenes","Calvo","Carvajal","Castro","Cordero","Fallas",
                  "Gamboa","Madrigal","Marin","Montero","Murillo","Nunez","Porras","Quesada","Segura","Villalobos"]

# ─── PANAMA ───
PA_EXTRA_MALE = ["Josue","Yovani","Erick","Abdiel","Alexis","Braulio","Dario","Edwin","Franklin","Gilberto",
                  "Humberto","Ismael","Jaime","Kendall","Leonel","Manuel","Norberto","Orlando","Pavel","Reynaldo"]
PA_EXTRA_FEMALE = ["Yamileth","Itzel","Keila","Mileika","Yaneth","Omaira","Zulay","Aracelis","Betzaida","Dayanara",
                    "Edith","Franchesca","Giselle","Hortencia","Indira","Johana","Kathia","Lineth","Mitzila","Nereida"]
PA_EXTRA_LAST = ["Gonzalez","Rodriguez","Martinez","Garcia","Lopez","Hernandez","Perez","Sanchez","Ramirez","Castillo",
                  "Morales","Diaz","Reyes","Mendez","Torres","Saldana","Batista","Caballero","De Gracia","Espino",
                  "Franco","Gaitan","Herrera","Jaen","Lasso","Moran","Navarro","Obaldia","Pittie","Quintero"]

# ─── URUGUAY ───
UY_EXTRA_MALE = ["Facundo","Thiago","Lautaro","Bautista","Santino","Valentino","Luciano","Nahuel","Maximo","Tobias",
                  "Ignacio","Agustin","Benicio","Gael","Ciro","Franco","Lisandro","Ramiro","Leandro","Gonzalo"]
UY_EXTRA_FEMALE = ["Sol","Martina","Lara","Pilar","Milagros","Candela","Rocio","Agustina","Micaela","Abril",
                    "Bianca","Aldana","Florencia","Jazmin","Oriana","Morena","Ludmila","Aylen","Celeste","Julieta"]
UY_EXTRA_LAST = ["Rodriguez","Gonzalez","Martinez","Garcia","Fernandez","Lopez","Perez","Alvarez","Suarez","Diaz",
                  "Silva","Gomez","Romero","Benitez","Sosa","Gimenez","Gutierrez","Medina","Castro","Acosta",
                  "Cabrera","Pereyra","Costa","Viera","Olivera","Ramos","Techera","Bentancor","Cardozo","Da Silva"]

# ─── CUBA ───
CU_EXTRA_MALE = ["Yoandri","Leinier","Yulieski","Dairon","Raisel","Yasiel","Yordanis","Osmany","Dayron","Yunior",
                  "Lazaro","Reinier","Yasmani","Yordan","Aledmys","Dariel","Erisbel","Frederich","Guillermo","Hector"]
CU_EXTRA_FEMALE = ["Yamilet","Dayanara","Lisandra","Yanelis","Daimy","Misleidy","Yoania","Gretel","Lisdey","Mayrelis",
                    "Odalys","Yuliesky","Ailyn","Dianelys","Leyanis","Mabel","Odalis","Taimara","Yanelys","Zunilda"]
CU_EXTRA_LAST = ["Rodriguez","Gonzalez","Hernandez","Garcia","Martinez","Lopez","Perez","Diaz","Sanchez","Fernandez",
                  "Torres","Alvarez","Ramirez","Cruz","Morales","Reyes","Gomez","Ruiz","Ramos","Castillo",
                  "Valdes","Cabrera","Herrera","Batista","Rivero","Prieto","Leyva","Acosta","Suarez","Dominguez"]

# ─── BOLIVIA ───
BO_EXTRA_MALE = ["Evo","Marcelo","Boris","Wilfredo","Jaime","Grover","Erwin","Limbert","Jhasmani","Romel",
                  "Elmer","Freddy","Jhonny","Limberth","Rolando","Waldo","Yerko","Alvaro","Bismarck","Carmelo"]
BO_EXTRA_FEMALE = ["Roxana","Maribel","Janeth","Yolanda","Cinthia","Nayeli","Jhosselin","Milenka","Rosemary","Wendy",
                    "Sdenka","Grecia","Lidia","Nilda","Primitiva","Reyna","Sinforosa","Tomasa","Vania","Wara"]
BO_EXTRA_LAST = ["Mamani","Quispe","Condori","Choque","Huanca","Flores","Apaza","Gutierrez","Gonzalez","Rodriguez",
                  "Rojas","Torrez","Mendoza","Vargas","Cruz","Garcia","Martinez","Morales","Perez","Arce",
                  "Calle","Chambi","Colque","Copa","Laura","Limachi","Nina","Paco","Tarqui","Yujra"]

# ─── PUERTO RICO ───
PR_EXTRA_MALE = ["Josean","Yariel","Jadiel","Abdiel","Jeidiel","Oziel","Natanael","Joangel","Jomar","Keishla",
                  "Kelvin","Jafet","Yandel","Joel","Emanuel","Janiel","Dereck","Ariel","Gadiel","Noel"]
PR_EXTRA_FEMALE = ["Yaritza","Keishla","Nalini","Yailenys","Kamila","Nayelis","Jailene","Yadira","Omayra","Damaris",
                    "Zulay","Aracelis","Nilsa","Wanda","Brunilda","Ivette","Kiara","Marielys","Nelida","Wilmarie"]
PR_EXTRA_LAST = ["Rodriguez","Martinez","Lopez","Garcia","Gonzalez","Rivera","Hernandez","Cruz","Torres","Diaz",
                  "Morales","Reyes","Santiago","Ortiz","Perez","Figueroa","Rosario","Colon","Vega","Maldonado",
                  "Ramos","Acevedo","Delgado","Serrano","Soto","Rios","Quinones","Medina","Navarro","Mercado"]


# ─── US (Census Bureau) ───
US_FIRST_MALE = [
    "James","Robert","John","Michael","David","William","Richard","Joseph","Thomas","Charles",
    "Christopher","Daniel","Matthew","Anthony","Mark","Donald","Steven","Paul","Andrew","Joshua",
    "Kenneth","Kevin","Brian","George","Timothy","Ronald","Edward","Jason","Jeffrey","Ryan",
    "Jacob","Gary","Nicholas","Eric","Jonathan","Stephen","Larry","Justin","Scott","Brandon",
    "Benjamin","Samuel","Raymond","Gregory","Frank","Alexander","Patrick","Jack","Dennis","Jerry",
    "Tyler","Aaron","Jose","Nathan","Henry","Peter","Adam","Douglas","Zachary","Walter",
    "Kyle","Harold","Carl","Gerald","Keith","Roger","Arthur","Terry","Sean","Christian",
    "Lawrence","Jesse","Dylan","Bryan","Joe","Jordan","Billy","Bruce","Albert","Eugene",
    "Ethan","Liam","Noah","Oliver","Elijah","Logan","Mason","Lucas","Jackson","Aiden",
    "Sebastian","Caleb","Owen","Carter","Luke","Jayden","Wyatt","Gabriel","Julian","Mateo",
    "Leo","Lincoln","Jaxon","Asher","Theodore","Josiah","Hudson","Miles","Ezra","Nolan",
    "Landon","Cooper","Kai","Cameron","Colton","Roman","Hunter","Dominic","Austin","Connor",
    "Carson","Declan","Adrian","Easton","Eli","Maverick","Parker","Xavier","Grayson","Bennett",
    "Ryder","Archer","Ian","Everett","Micah","Axel","Emmett","Sawyer","Wesley","Silas",
    "Brooks","Rowan","Kingston","Grant","Beau","Cole","Dean","Chase","Harrison","Max",
]
US_FIRST_FEMALE = [
    "Mary","Patricia","Jennifer","Linda","Barbara","Elizabeth","Susan","Jessica","Sarah","Karen",
    "Lisa","Nancy","Betty","Margaret","Sandra","Ashley","Dorothy","Kimberly","Emily","Donna",
    "Michelle","Carol","Amanda","Melissa","Deborah","Stephanie","Rebecca","Sharon","Laura","Cynthia",
    "Kathleen","Amy","Angela","Shirley","Anna","Brenda","Pamela","Emma","Nicole","Helen",
    "Samantha","Katherine","Christine","Rachel","Maria","Heather","Diane","Ruth","Julie","Olivia",
    "Joyce","Virginia","Victoria","Kelly","Lauren","Christina","Joan","Evelyn","Megan","Andrea",
    "Cheryl","Hannah","Jacqueline","Martha","Gloria","Teresa","Sara","Madison","Frances","Kathryn",
    "Sophia","Mia","Charlotte","Amelia","Harper","Ella","Scarlett","Grace","Chloe","Aria",
    "Lily","Zoey","Penelope","Layla","Nora","Camila","Lillian","Addison","Eleanor","Natalie",
    "Lucy","Stella","Savannah","Aubrey","Brooklyn","Leah","Claire","Violet","Aurora","Hazel",
    "Audrey","Bella","Luna","Ellie","Paisley","Skylar","Ruby","Madelyn","Naomi","Eva",
    "Piper","Taylor","Willow","Madeline","Kennedy","Quinn","Maya","Mackenzie","Molly","Reagan",
    "Cora","Bailey","Ivy","Aaliyah","Lyla","Alexandra","Vivian","Autumn","Gianna","Emilia",
    "Valentina","Clara","Jade","Josephine","Kinsley","Delilah","Arianna","Morgan","Allison","Alexa",
]
US_LAST = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez",
    "Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin",
    "Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson",
    "Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores",
    "Green","Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell","Carter","Roberts",
    "Gomez","Phillips","Evans","Turner","Diaz","Parker","Cruz","Edwards","Collins","Reyes",
    "Stewart","Morris","Morales","Murphy","Cook","Rogers","Peterson","Morgan","Cooper","Reed",
    "Bailey","Bell","Howard","Ward","Sanders","Price","Barnes","Ross","Henderson","Coleman",
    "Jenkins","Perry","Powell","Long","Patterson","Hughes","Washington","Butler","Simmons","Foster",
    "Gonzales","Bryant","Alexander","Russell","Griffin","Hayes","Myers","Ford","Hamilton","Graham",
    "Sullivan","Wallace","Woods","West","Jordan","Owens","Reynolds","Fisher","Ellis","Harrison",
    "Gibson","McDonald","Mills","Warren","Stone","Wagner","Cole","Hunt","Black","Palmer",
    "Webb","Simpson","Stevens","Crawford","Hicks","Holmes","Rice","Douglas","Chapman","Knight",
    "Franklin","Andrews","Lawrence","Oliver","Grant","Rose","Harper","Fox","Bishop","Tucker",
]

# ─── BRAZIL (IBGE) ───
BR_FIRST_MALE = [
    "Joao","Jose","Antonio","Francisco","Carlos","Paulo","Pedro","Lucas","Marcos","Luiz",
    "Gabriel","Rafael","Daniel","Marcelo","Bruno","Eduardo","Felipe","Gustavo","Ricardo","Fernando",
    "Rodrigo","Matheus","Leonardo","Andre","Diego","Thiago","Guilherme","Fabio","Vinicius","Alexandre",
    "Leandro","Caio","Henrique","Renato","Roberto","Sergio","Mauricio","Igor","Marcio","Victor",
    "Julio","Wellington","Adriano","Sandro","Douglas","Renan","Rogerio","Samuel","Miguel","Arthur",
    "Bernardo","Davi","Enzo","Heitor","Lorenzo","Theo","Pietro","Nicolas","Otavio","Luan",
    "Nathan","Murilo","Breno","Ian","Yuri","Raul","Ryan","Kevin","Bryan","Pablo",
    "Tales","Danilo","Anderson","Alex","Elias","Claudio","Benedito","Geraldo","Nilson","Edson",
    "Nelson","Raimundo","Sebastiao","Manoel","Joaquim","Almir","Evandro","Jair","Cleber","Luciano",
    "Emerson","Willian","Tiago","Mateus","Emanuel","Moises","Cristiano","Wallace","Wesley","Giovanni",
]
BR_FIRST_FEMALE = [
    "Maria","Ana","Juliana","Fernanda","Adriana","Patricia","Camila","Mariana","Aline","Amanda",
    "Bruna","Carolina","Tatiana","Leticia","Gabriela","Daniela","Vanessa","Luciana","Beatriz","Renata",
    "Priscila","Raquel","Sandra","Simone","Cristiane","Fabiana","Andreia","Rosana","Carla","Erica",
    "Thais","Natalia","Larissa","Laura","Isabella","Sophia","Alice","Manuela","Helena","Valentina",
    "Luisa","Livia","Lorena","Isadora","Clara","Cecilia","Lara","Marina","Nicole","Rafaela",
    "Giovanna","Bianca","Vitoria","Sara","Yasmin","Rebeca","Eduarda","Milena","Emanuella","Luana",
    "Jessica","Monique","Viviane","Michele","Elaine","Claudia","Monica","Solange","Regina","Vera",
    "Rosangela","Aparecida","Francisca","Raimunda","Lucia","Tereza","Sueli","Neusa","Denise","Joana",
    "Flavia","Roberta","Sabrina","Ingrid","Karen","Talita","Debora","Cintia","Barbara","Catarina",
    "Diana","Elisa","Flora","Graziela","Heloisa","Iris","Jaqueline","Kelly","Mirella","Paloma",
]
BR_LAST = [
    "Silva","Santos","Oliveira","Souza","Rodrigues","Ferreira","Alves","Pereira","Lima","Gomes",
    "Costa","Ribeiro","Martins","Carvalho","Almeida","Lopes","Soares","Fernandes","Vieira","Barbosa",
    "Rocha","Dias","Nascimento","Andrade","Moreira","Nunes","Marques","Machado","Mendes","Freitas",
    "Cardoso","Ramos","Goncalves","Santana","Teixeira","Araujo","Pinto","Barros","Correia","Campos",
    "Castro","Moura","Monteiro","Duarte","Reis","Batista","Miranda","Cunha","Nogueira","Azevedo",
    "Cavalcanti","Peixoto","Aguiar","Melo","Fonseca","Brito","Coelho","Tavares","Jesus","Borges",
    "Leal","Porto","Xavier","Medeiros","Pires","Sampaio","Amaral","Figueiredo","Guimaraes","Queiroz",
    "Bastos","Carneiro","Macedo","Paiva","Resende","Siqueira","Toledo","Vasconcelos","Braga","Lacerda",
    "Moraes","Neves","Pacheco","Pimentel","Rego","Serra","Vargas","Ventura","Alencar","Barreto",
    "Coutinho","Franco","Leite","Menezes","Nobrega","Prado","Rangel","Santiago","Teles","Valente",
]

# ─── CANADA (StatCan EN+FR) ───
CA_FIRST_MALE = [
    "Liam","Noah","Oliver","William","Benjamin","Elijah","James","Lucas","Mason","Ethan",
    "Alexandre","Gabriel","Samuel","Nathan","Leo","Thomas","Felix","Raphael","Jacob","Logan",
    "Jack","Owen","Daniel","Henry","Ryan","Matthew","Jayden","Carter","Aiden","Alexander",
    "Theodore","Sebastian","Caleb","Eli","Miles","Luca","Hunter","Dylan","Jackson","Cameron",
    "Connor","Adam","Nolan","Xavier","Cooper","Emmett","Finn","Gavin","Harrison","Tristan",
    "Maxime","Emile","Antoine","Olivier","Louis","Charles","Mathis","Hugo","Arthur","Theo",
    "Elliot","Zachary","Parker","Wyatt","Cole","Chase","Beau","Max","Ian","Jasper",
    "Jace","Carson","Kai","Lincoln","Adrian","Maverick","Sawyer","Bennett","Wesley","Austin",
    "Blake","Dominic","Brandon","Justin","Scott","Tyler","Kyle","Trevor","Derek","Jason",
    "Philippe","Francois","Jean","Pierre","Yves","Andre","Michel","Claude","Denis","Marc",
]
CA_FIRST_FEMALE = [
    "Olivia","Emma","Charlotte","Amelia","Sophia","Ava","Mia","Isla","Evelyn","Luna",
    "Harper","Ella","Chloe","Lily","Scarlett","Aria","Madison","Zoey","Penelope","Layla",
    "Alice","Florence","Lea","Camille","Rosalie","Juliette","Madeleine","Aurelie","Emilie","Noemie",
    "Victoria","Grace","Abigail","Emily","Sofia","Riley","Nora","Hannah","Aubrey","Brooklyn",
    "Eleanor","Stella","Natalie","Leah","Claire","Violet","Aurora","Hazel","Lucy","Audrey",
    "Ellie","Paisley","Sadie","Nova","Willow","Ruby","Quinn","Maya","Ivy","Adalyn",
    "Isabelle","Gabrielle","Sophie","Laurence","Maude","Jade","Simone","Elodie","Ariane","Katherine",
    "Mackenzie","Samantha","Jasmine","Taylor","Morgan","Brooke","Paige","Savannah","Megan","Lauren",
    "Rachel","Nicole","Andrea","Chelsea","Cassidy","Kira","Brielle","Avery","Addison","Marguerite",
    "Colette","Genevieve","Dominique","Monique","Renee","Sylvie","Danielle","Valerie","Annick","Marie",
]
CA_LAST = [
    "Smith","Brown","Wilson","Johnson","Williams","Jones","Taylor","Martin","Anderson","Thomas",
    "Jackson","White","Harris","Robinson","Thompson","Clark","Lewis","Young","Walker","Hall",
    "Campbell","Mitchell","Stewart","Turner","Baker","Morgan","Lee","King","Scott","Green",
    "Adams","Nelson","Carter","Collins","Murphy","Davis","Miller","Moore","Kelly","Ward",
    "Tremblay","Gagnon","Roy","Cote","Bouchard","Gauthier","Morin","Lavoie","Fortin","Gagne",
    "Ouellet","Pelletier","Belanger","Levesque","Bergeron","Leblanc","Paquette","Girard","Simard","Boucher",
    "Caron","Beaulieu","Cloutier","Dube","Poirier","Fontaine","Lapointe","Lefebvre","Lemieux","Martel",
    "MacDonald","MacLeod","MacKenzie","MacKinnon","MacLean","Fraser","Cameron","MacPherson","Henderson","Ross",
    "Grant","Russell","Murray","Robertson","Watson","Morrison","Hamilton","Craig","Duncan","Gray",
    "Burns","Reid","Gordon","Douglas","Graham","McDonald","Fleming","Harvey","Marsh","Spencer",
]


def generate_pack_gendered(first_names, last_names, count=25000):
    """Generate unique first,last combos from a single-gender first name list."""
    combos = set()
    max_possible = len(first_names) * len(last_names)
    target = min(count, max_possible)
    attempts = 0
    while len(combos) < target and attempts < target * 10:
        first = random.choice(first_names)
        last = random.choice(last_names)
        combos.add((first, last))
        attempts += 1
    return sorted(combos)


def generate_pack_mix(first_male, first_female, last_names, count=50000):
    """Generate unique first,last combos from BOTH male + female names."""
    all_first = first_male + first_female
    combos = set()
    max_possible = len(all_first) * len(last_names)
    target = min(count, max_possible)
    attempts = 0
    while len(combos) < target and attempts < target * 10:
        first = random.choice(all_first)
        last = random.choice(last_names)
        combos.add((first, last))
        attempts += 1
    return sorted(combos)


def expand_last_names(base_lasts):
    """
    Expand last name list with compound last names (culturally authentic).
    In Latin America, Spain, Brazil, etc. people commonly use two last names
    (paternal + maternal), e.g. 'Garcia Rodriguez', 'Martinez Lopez'.
    This multiplies available combos significantly.
    """
    expanded = list(base_lasts)  # Keep all single last names
    # Add compound last names (pick pairs that sound natural)
    compound_count = 0
    seen = set(expanded)
    shuffled = list(base_lasts)
    random.shuffle(shuffled)
    for i in range(len(shuffled)):
        for j in range(len(shuffled)):
            if i == j:
                continue
            compound = f"{shuffled[i]} {shuffled[j]}"
            if compound not in seen:
                expanded.append(compound)
                seen.add(compound)
                compound_count += 1
                if len(expanded) >= 500:  # Cap at 500 last names
                    return expanded
    return expanded


def expand_last_names_en(base_lasts):
    """Expand English last names with hyphenated compounds (Smith-Jones)."""
    expanded = list(base_lasts)
    seen = set(expanded)
    shuffled = list(base_lasts)
    random.shuffle(shuffled)
    for i in range(len(shuffled)):
        for j in range(i + 1, len(shuffled)):
            compound = f"{shuffled[i]}-{shuffled[j]}"
            if compound not in seen:
                expanded.append(compound)
                seen.add(compound)
                if len(expanded) >= 500:
                    return expanded
    return expanded


def build_country_data(extra_male, extra_female, extra_last):
    """Combine shared LATAM base names with country-specific extras + compound lasts."""
    males = list(set(SPANISH_MALE_COMMON + extra_male))
    females = list(set(SPANISH_FEMALE_COMMON + extra_female))
    base_lasts = list(set(LATAM_COMMON_LAST + extra_last))
    lasts = expand_last_names(base_lasts)
    return males, females, lasts


def write_pack(path, combos, label):
    """Write a name pack file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {label} -- {len(combos)} unique combos\n")
        for first, last in combos:
            f.write(f"{first},{last}\n")


def generate_3_packs(base_name, males, females, lasts, out_dir):
    """
    Generate 3 packs for a country:
      - {base}_M_25k.txt  (25000 male-only first names)
      - {base}_F_25k.txt  (25000 female-only first names)
      - {base}_Mix_50k.txt (50000 mixed first names)
    Returns total names generated.
    """
    total = 0

    # Male pack
    m_combos = generate_pack_gendered(males, lasts, 25000)
    m_file = f"{base_name}_M_25k.txt"
    write_pack(os.path.join(out_dir, m_file), m_combos, m_file)
    print(f"  {m_file}: {len(m_combos)} names ({len(males)} male x {len(lasts)} last)")
    total += len(m_combos)

    # Female pack
    f_combos = generate_pack_gendered(females, lasts, 25000)
    f_file = f"{base_name}_F_25k.txt"
    write_pack(os.path.join(out_dir, f_file), f_combos, f_file)
    print(f"  {f_file}: {len(f_combos)} names ({len(females)} female x {len(lasts)} last)")
    total += len(f_combos)

    # Mix pack (male + female combined = 50k target)
    mix_combos = generate_pack_mix(males, females, lasts, 50000)
    mix_file = f"{base_name}_Mix_50k.txt"
    write_pack(os.path.join(out_dir, mix_file), mix_combos, mix_file)
    print(f"  {mix_file}: {len(mix_combos)} names ({len(males)}m + {len(females)}f x {len(lasts)} last)")
    total += len(mix_combos)

    return total


def main():
    # ─── Define all packs ───
    MX_EXTRA_MALE = [
        "Josue","Erick","Omar","Aaron","Saul","Uriel","Missael","Noe","Jesus","Christian",
        "Jonathan","Edgar","Said","Alexis","Brandon","Kevin","Angel","Obed","Gael","Iker",
    ]
    MX_EXTRA_FEMALE = [
        "Itzel","Arely","Nayeli","Estrella","Sol","Libertad","Celeste","Abril","Luz","Juana",
        "Aurora","Soledad","Lourdes","Hortensia","Raquel","Irene","Julia","Marina","Noemi","Kenya",
    ]
    MX_EXTRA_LAST = [
        "Orozco","Guzman","Salazar","Acosta","Espinoza","Luna","Ochoa","Cervantes","Silva","Rojas",
        "Escobar","Cortes","Velazquez","Palacios","Campos","Valencia","Avila","Maldonado","Zamora","Sandoval",
        "Mejia","Leon","Montoya","Paredes","Pena","Montes","Dominguez","Cardenas","Ibarra","Miranda",
        "Serrano","Figueroa","Molina","Pacheco","Camacho","Cabrera","Trujillo","Mora","Bravo","Rangel",
        "Salinas","Bautista","Ponce","Cisneros","Magana","Cuevas","Villalobos","Saavedra","Barajas","Amaya",
        "Duarte","Macias","Chavez","Rosas","Aguirre","Leal","Nava","Parra","Estrada","Montalvo",
    ]

    latam_countries = {
        "mexico": (MX_EXTRA_MALE, MX_EXTRA_FEMALE, MX_EXTRA_LAST),
        "colombia": (CO_EXTRA_MALE, CO_EXTRA_FEMALE, CO_EXTRA_LAST),
        "argentina": (AR_EXTRA_MALE, AR_EXTRA_FEMALE, AR_EXTRA_LAST),
        "peru": (PE_EXTRA_MALE, PE_EXTRA_FEMALE, PE_EXTRA_LAST),
        "venezuela": (VE_EXTRA_MALE, VE_EXTRA_FEMALE, VE_EXTRA_LAST),
        "chile": (CL_EXTRA_MALE, CL_EXTRA_FEMALE, CL_EXTRA_LAST),
        "ecuador": (EC_EXTRA_MALE, EC_EXTRA_FEMALE, EC_EXTRA_LAST),
        "guatemala": (GT_EXTRA_MALE, GT_EXTRA_FEMALE, GT_EXTRA_LAST),
        "dominican": (DO_EXTRA_MALE, DO_EXTRA_FEMALE, DO_EXTRA_LAST),
        "honduras": (HN_EXTRA_MALE, HN_EXTRA_FEMALE, HN_EXTRA_LAST),
        "paraguay": (PY_EXTRA_MALE, PY_EXTRA_FEMALE, PY_EXTRA_LAST),
        "el_salvador": (SV_EXTRA_MALE, SV_EXTRA_FEMALE, SV_EXTRA_LAST),
        "nicaragua": (NI_EXTRA_MALE, NI_EXTRA_FEMALE, NI_EXTRA_LAST),
        "costa_rica": (CR_EXTRA_MALE, CR_EXTRA_FEMALE, CR_EXTRA_LAST),
        "panama": (PA_EXTRA_MALE, PA_EXTRA_FEMALE, PA_EXTRA_LAST),
        "uruguay": (UY_EXTRA_MALE, UY_EXTRA_FEMALE, UY_EXTRA_LAST),
        "cuba": (CU_EXTRA_MALE, CU_EXTRA_FEMALE, CU_EXTRA_LAST),
        "bolivia": (BO_EXTRA_MALE, BO_EXTRA_FEMALE, BO_EXTRA_LAST),
        "puerto_rico": (PR_EXTRA_MALE, PR_EXTRA_FEMALE, PR_EXTRA_LAST),
    }

    # Non-LATAM packs (standalone data)
    standalone = {
        "us_names": (US_FIRST_MALE, US_FIRST_FEMALE, US_LAST),
        "brazil": (BR_FIRST_MALE, BR_FIRST_FEMALE, BR_LAST),
        "canada": (CA_FIRST_MALE, CA_FIRST_FEMALE, CA_LAST),
        "uk": (UK_FIRST_MALE, UK_FIRST_FEMALE, UK_LAST),
        "india": (IN_FIRST_MALE, IN_FIRST_FEMALE, IN_LAST),
        "philippines": (PH_FIRST_MALE, PH_FIRST_FEMALE, PH_LAST),
    }

    # Countries with non-compound last name traditions
    standalone_nocompound = {
        "russia": (RU_FIRST_MALE, RU_FIRST_FEMALE, RU_LAST),
        "egypt": (EG_FIRST_MALE, EG_FIRST_FEMALE, EG_LAST),
        "nigeria": (NG_FIRST_MALE, NG_FIRST_FEMALE, NG_LAST),
        "south_africa": (ZA_FIRST_MALE, ZA_FIRST_FEMALE, ZA_LAST),
        "arab": (AR_FIRST_MALE_ARAB, AR_FIRST_FEMALE_ARAB, AR_LAST_ARAB),
        "turkey": (TR_FIRST_MALE, TR_FIRST_FEMALE, TR_LAST),
    }

    out_dir = os.path.join(os.path.dirname(__file__), "data", "names")
    os.makedirs(out_dir, exist_ok=True)

    total_names = 0
    total_packs = 0

    # Generate LATAM packs (base + extras) — 3 per country
    for country, (extra_m, extra_f, extra_l) in latam_countries.items():
        print(f"\n── {country.upper()} ──")
        males, females, lasts = build_country_data(extra_m, extra_f, extra_l)
        total_names += generate_3_packs(country, males, females, lasts, out_dir)
        total_packs += 3

    # Generate standalone packs --- 3 per country (with EN-style compound lasts)
    for country, (males, females, lasts) in standalone.items():
        print(f"\n-- {country.upper()} --")
        expanded_lasts = expand_last_names_en(list(lasts))
        total_names += generate_3_packs(country, list(males), list(females), expanded_lasts, out_dir)
        total_packs += 3

    # Generate packs for countries that use expand_last_names (space-separated compounds)
    for country, (males, females, lasts) in standalone_nocompound.items():
        print(f"\n-- {country.upper()} --")
        expanded_lasts = expand_last_names(list(lasts))
        total_names += generate_3_packs(country, list(males), list(females), expanded_lasts, out_dir)
        total_packs += 3

    print(f"\n{'='*50}")
    print(f"Total: {total_names} names across {total_packs} packs")
    print(f"({total_packs // 3} countries × 3 packs each: M, F, Mix)")


if __name__ == "__main__":
    main()
