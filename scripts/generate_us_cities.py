"""
Generate data/us_cities.json — sorted list of major US cities for the city typeahead.

Usage:
  python3 scripts/generate_us_cities.py

If data/uscities.csv (SimpleMaps free tier) is present, uses it to generate a full
~900-city list. Otherwise falls back to the built-in curated list (~300 cities).

SimpleMaps free CSV download: https://simplemaps.com/data/us-cities
  → Download "Basic" → place uscities.csv in data/
"""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_CSV_PATH = _ROOT / "data" / "uscities.csv"
_OUT_PATH = _ROOT / "data" / "us_cities.json"

_MIN_POP = 10_000

# Curated fallback: ~300 major/popular US cities covering all states + common day-trip destinations.
# Sorted roughly by population; typeahead UX works fine at this size.
_BUILTIN_CITIES: list[tuple[str, str, int]] = [
    ("New York", "NY", 8336817), ("Los Angeles", "CA", 3979576), ("Chicago", "IL", 2693976),
    ("Houston", "TX", 2320268), ("Phoenix", "AZ", 1680992), ("Philadelphia", "PA", 1584064),
    ("San Antonio", "TX", 1547253), ("San Diego", "CA", 1423851), ("Dallas", "TX", 1343573),
    ("San Jose", "CA", 1021795), ("Austin", "TX", 961855), ("Jacksonville", "FL", 903889),
    ("Fort Worth", "TX", 918915), ("Columbus", "OH", 898553), ("Charlotte", "NC", 885708),
    ("Indianapolis", "IN", 876384), ("San Francisco", "CA", 873965), ("Seattle", "WA", 737255),
    ("Denver", "CO", 715522), ("Nashville", "TN", 689447), ("Oklahoma City", "OK", 681054),
    ("El Paso", "TX", 678815), ("Washington", "DC", 705749), ("Boston", "MA", 692600),
    ("Las Vegas", "NV", 651319), ("Louisville", "KY", 633045), ("Baltimore", "MD", 585708),
    ("Milwaukee", "WI", 590157), ("Albuquerque", "NM", 564559), ("Tucson", "AZ", 545975),
    ("Fresno", "CA", 530093), ("Sacramento", "CA", 513624), ("Mesa", "AZ", 504258),
    ("Kansas City", "MO", 495327), ("Atlanta", "GA", 498715), ("Omaha", "NE", 486051),
    ("Colorado Springs", "CO", 478961), ("Raleigh", "NC", 469298), ("Long Beach", "CA", 462628),
    ("Virginia Beach", "VA", 459470), ("Minneapolis", "MN", 429954), ("Tampa", "FL", 399700),
    ("New Orleans", "LA", 383997), ("Arlington", "TX", 394266), ("Bakersfield", "CA", 383579),
    ("Honolulu", "HI", 350395), ("Anaheim", "CA", 346997), ("Aurora", "CO", 366623),
    ("Santa Ana", "CA", 332725), ("Corpus Christi", "TX", 326586), ("Riverside", "CA", 330063),
    ("St. Louis", "MO", 300576), ("Lexington", "KY", 322570), ("Pittsburgh", "PA", 300286),
    ("Stockton", "CA", 311034), ("Cincinnati", "OH", 303940), ("Anchorage", "AK", 288000),
    ("Henderson", "NV", 320189), ("Greensboro", "NC", 299035), ("Plano", "TX", 288061),
    ("Newark", "NJ", 282011), ("Toledo", "OH", 270871), ("Orlando", "FL", 307573),
    ("St. Paul", "MN", 308096), ("Chula Vista", "CA", 274492), ("Fort Wayne", "IN", 270402),
    ("Chandler", "AZ", 261165), ("Madison", "WI", 259680), ("Scottsdale", "AZ", 258069),
    ("Laredo", "TX", 255205), ("Lubbock", "TX", 257141), ("Durham", "NC", 278993),
    ("Buffalo", "NY", 255805), ("Reno", "NV", 250998), ("Winston-Salem", "NC", 249545),
    ("Gilbert", "AZ", 248279), ("Glendale", "AZ", 248325), ("North Las Vegas", "NV", 262527),
    ("Garland", "TX", 234566), ("Irving", "TX", 240373), ("Hialeah", "FL", 224669),
    ("Chesapeake", "VA", 244835), ("Fremont", "CA", 230504), ("Richmond", "VA", 226610),
    ("Baton Rouge", "LA", 225374), ("Boise", "ID", 235684), ("Spokane", "WA", 222081),
    ("Des Moines", "IA", 217521), ("Tacoma", "WA", 217827), ("San Bernardino", "CA", 215941),
    ("Modesto", "CA", 218464), ("Fontana", "CA", 214547), ("Moreno Valley", "CA", 213055),
    ("Columbus", "GA", 201840), ("Glendale", "CA", 201020), ("Akron", "OH", 190469),
    ("Huntington Beach", "CA", 198711), ("Little Rock", "AR", 197992), ("Birmingham", "AL", 215006),
    ("Grand Rapids", "MI", 198917), ("Salt Lake City", "UT", 200567), ("Tallahassee", "FL", 196169),
    ("Huntsville", "AL", 215006), ("Worcester", "MA", 185877), ("Knoxville", "TN", 187347),
    ("Providence", "RI", 178042), ("Mobile", "AL", 187041), ("Oxnard", "CA", 202063),
    ("Tempe", "AZ", 195805), ("Overland Park", "KS", 197238), ("Shreveport", "LA", 187593),
    ("Augusta", "GA", 202081), ("Garden Grove", "CA", 171949), ("Oceanside", "CA", 167148),
    ("Rancho Cucamonga", "CA", 177751), ("Santa Clarita", "CA", 228673), ("Lancaster", "CA", 173516),
    ("Ontario", "CA", 175265), ("Elk Grove", "CA", 176124), ("Fort Collins", "CO", 164245),
    ("Palmdale", "CA", 169450), ("Salem", "OR", 175535), ("Eugene", "OR", 172622),
    ("Corona", "CA", 169868), ("Chattanooga", "TN", 180557), ("Jackson", "MS", 166965),
    ("Cape Coral", "FL", 194016), ("Peoria", "IL", 111388), ("Syracuse", "NY", 142553),
    ("Elk Grove", "CA", 176124), ("Springfield", "MO", 167882), ("Hampton", "VA", 137436),
    ("Durham", "NC", 278993), ("Warren", "MI", 134873), ("Mesquite", "TX", 143930),
    ("Surprise", "AZ", 148553), ("Paterson", "NJ", 145233), ("Roseville", "CA", 141500),
    ("Torrance", "CA", 142447), ("Pasadena", "TX", 154000), ("Denton", "TX", 148146),
    ("Hayward", "CA", 162954), ("Lakewood", "CO", 155984), ("Clarksville", "TN", 166722),
    ("Pomona", "CA", 151348), ("Alexandria", "VA", 159299), ("Macon", "GA", 153159),
    ("Dayton", "OH", 140444), ("Sunnyvale", "CA", 152258), ("Hollywood", "FL", 153627),
    ("Frisco", "TX", 200490), ("McKinney", "TX", 199177), ("Killeen", "TX", 153095),
    ("Pasadena", "CA", 141029), ("Murfreesboro", "TN", 152769), ("Fort Lauderdale", "FL", 182760),
    ("Bridgeport", "CT", 145014), ("Amarillo", "TX", 201818), ("Pembroke Pines", "FL", 170307),
    ("Escondido", "CA", 151038), ("Kansas City", "KS", 155564), ("Savannah", "GA", 144352),
    ("Bellevue", "WA", 145300), ("Salinas", "CA", 163542), ("Surprise", "AZ", 148553),
    ("Ontario", "CA", 175265), ("Fullerton", "CA", 143617), ("Visalia", "CA", 141384),
    ("Beaumont", "TX", 118228), ("Orange", "CA", 140293), ("Thornton", "CO", 136208),
    ("Aurora", "IL", 178994), ("Rockford", "IL", 145609), ("Joliet", "IL", 147433),
    ("Naperville", "IL", 148449), ("Lancaster", "PA", 60063), ("Springfield", "IL", 117352),
    ("Hartford", "CT", 122587), ("New Haven", "CT", 130250), ("Stamford", "CT", 135470),
    ("Waterbury", "CT", 115340), ("Bridgeport", "CT", 145014), ("Yonkers", "NY", 200810),
    ("Rochester", "NY", 208046), ("Albany", "NY", 97856), ("Schenectady", "NY", 65506),
    ("Utica", "NY", 59750), ("Troy", "NY", 49170), ("Buffalo", "NY", 255805),
    ("Jersey City", "NJ", 292449), ("Elizabeth", "NJ", 132790), ("Trenton", "NJ", 83203),
    ("Camden", "NJ", 74420), ("Allentown", "PA", 125845), ("Reading", "PA", 95112),
    ("Erie", "PA", 94831), ("Scranton", "PA", 76997), ("Altoona", "PA", 43453),
    ("Portsmouth", "VA", 95535), ("Norfolk", "VA", 244703), ("Newport News", "VA", 183412),
    ("Roanoke", "VA", 99143), ("Charlottesville", "VA", 46553), ("Fredericksburg", "VA", 29916),
    ("Wilmington", "DE", 70166), ("Dover", "DE", 38079), ("Annapolis", "MD", 40812),
    ("Frederick", "MD", 78171), ("Rockville", "MD", 68636), ("Bethesda", "MD", 62223),
    ("Gaithersburg", "MD", 68745), ("Columbia", "MD", 103084), ("Baltimore", "MD", 585708),
    ("Charlotte", "NC", 885708), ("Fayetteville", "NC", 211657), ("Cary", "NC", 170282),
    ("Wilmington", "NC", 123784), ("High Point", "NC", 114059), ("Asheville", "NC", 94589),
    ("Columbus", "SC", 131674), ("Charleston", "SC", 150227), ("Greenville", "SC", 70635),
    ("Columbia", "SC", 136362), ("Augusta", "GA", 202081), ("Athens", "GA", 126913),
    ("Macon", "GA", 153159), ("Albany", "GA", 73934), ("Gainesville", "FL", 133997),
    ("Pensacola", "FL", 54312), ("St. Petersburg", "FL", 265351), ("Miami", "FL", 467963),
    ("Hialeah", "FL", 224669), ("Coral Springs", "FL", 133507), ("Clearwater", "FL", 117292),
    ("Lakeland", "FL", 112641), ("West Palm Beach", "FL", 117415), ("Palm Bay", "FL", 119760),
    ("Miramar", "FL", 140823), ("Memphis", "TN", 650910), ("Louisville", "KY", 633045),
    ("Lexington", "KY", 322570), ("Bowling Green", "KY", 72294), ("Covington", "KY", 40640),
    ("Indianapolis", "IN", 876384), ("Fort Wayne", "IN", 270402), ("Evansville", "IN", 117979),
    ("South Bend", "IN", 102685), ("Gary", "IN", 69093), ("Carmel", "IN", 101068),
    ("Detroit", "MI", 670031), ("Grand Rapids", "MI", 198917), ("Warren", "MI", 134873),
    ("Sterling Heights", "MI", 134346), ("Ann Arbor", "MI", 123851), ("Lansing", "MI", 112644),
    ("Flint", "MI", 96448), ("Dearborn", "MI", 90003), ("Livonia", "MI", 93970),
    ("Columbus", "OH", 898553), ("Cleveland", "OH", 381009), ("Cincinnati", "OH", 303940),
    ("Toledo", "OH", 270871), ("Akron", "OH", 190469), ("Dayton", "OH", 140444),
    ("Parma", "OH", 77979), ("Canton", "OH", 71741), ("Youngstown", "OH", 64428),
    ("Milwaukee", "WI", 590157), ("Madison", "WI", 259680), ("Green Bay", "WI", 107395),
    ("Kenosha", "WI", 99218), ("Racine", "WI", 76313), ("Appleton", "WI", 75644),
    ("Minneapolis", "MN", 429954), ("St. Paul", "MN", 308096), ("Rochester", "MN", 121395),
    ("Duluth", "MN", 89127), ("Bloomington", "MN", 89987), ("Plymouth", "MN", 79828),
    ("Sioux Falls", "SD", 192517), ("Rapid City", "SD", 74703), ("Fargo", "ND", 124662),
    ("Grand Forks", "ND", 57056), ("Bismarck", "ND", 73622), ("Billings", "MT", 109550),
    ("Missoula", "MT", 73489), ("Great Falls", "MT", 59351), ("Casper", "WY", 57461),
    ("Cheyenne", "WY", 63957), ("Boise", "ID", 235684), ("Nampa", "ID", 99321),
    ("Idaho Falls", "ID", 62888), ("Pocatello", "ID", 56216), ("Salt Lake City", "UT", 200567),
    ("West Valley City", "UT", 140230), ("Provo", "UT", 115919), ("West Jordan", "UT", 116961),
    ("Orem", "UT", 97499), ("Sandy", "UT", 96184), ("Ogden", "UT", 87321),
    ("Las Vegas", "NV", 651319), ("Henderson", "NV", 320189), ("North Las Vegas", "NV", 262527),
    ("Reno", "NV", 250998), ("Sparks", "NV", 102895), ("Carson City", "NV", 55916),
    ("Phoenix", "AZ", 1680992), ("Tucson", "AZ", 545975), ("Mesa", "AZ", 504258),
    ("Chandler", "AZ", 261165), ("Scottsdale", "AZ", 258069), ("Glendale", "AZ", 248325),
    ("Gilbert", "AZ", 248279), ("Tempe", "AZ", 195805), ("Peoria", "AZ", 190985),
    ("Surprise", "AZ", 148553), ("Flagstaff", "AZ", 73964), ("Sedona", "AZ", 10336),
    ("Albuquerque", "NM", 564559), ("Las Cruces", "NM", 112200), ("Rio Rancho", "NM", 104046),
    ("Santa Fe", "NM", 84683), ("Roswell", "NM", 48366), ("Farmington", "NM", 45426),
    ("Denver", "CO", 715522), ("Colorado Springs", "CO", 478961), ("Aurora", "CO", 366623),
    ("Fort Collins", "CO", 164245), ("Lakewood", "CO", 155984), ("Thornton", "CO", 136208),
    ("Arvada", "CO", 118428), ("Westminster", "CO", 113479), ("Pueblo", "CO", 108249),
    ("Boulder", "CO", 105119), ("Greeley", "CO", 103990), ("Longmont", "CO", 92858),
    ("Loveland", "CO", 78877), ("Broomfield", "CO", 74112), ("Vail", "CO", 5474),
    ("Aspen", "CO", 7004), ("Telluride", "CO", 2488), ("Durango", "CO", 19071),
    ("Omaha", "NE", 486051), ("Lincoln", "NE", 289102), ("Bellevue", "NE", 63780),
    ("Grand Island", "NE", 52560), ("Kearney", "NE", 33790), ("Fremont", "NE", 26764),
    ("Wichita", "KS", 389938), ("Overland Park", "KS", 197238), ("Kansas City", "KS", 155564),
    ("Topeka", "KS", 125963), ("Olathe", "KS", 140545), ("Lawrence", "KS", 96892),
    ("Oklahoma City", "OK", 681054), ("Tulsa", "OK", 413066), ("Norman", "OK", 128026),
    ("Broken Arrow", "OK", 113540), ("Edmond", "OK", 93757), ("Lawton", "OK", 93967),
    ("Dallas", "TX", 1343573), ("Houston", "TX", 2320268), ("San Antonio", "TX", 1547253),
    ("Austin", "TX", 961855), ("El Paso", "TX", 678815), ("Fort Worth", "TX", 918915),
    ("Arlington", "TX", 394266), ("Corpus Christi", "TX", 326586), ("Plano", "TX", 288061),
    ("Laredo", "TX", 255205), ("Lubbock", "TX", 257141), ("Garland", "TX", 234566),
    ("Irving", "TX", 240373), ("Amarillo", "TX", 201818), ("Mesquite", "TX", 143930),
    ("McKinney", "TX", 199177), ("Frisco", "TX", 200490), ("Killeen", "TX", 153095),
    ("Waco", "TX", 138183), ("Denton", "TX", 148146), ("Midland", "TX", 146038),
    ("Odessa", "TX", 118504), ("McAllen", "TX", 142210), ("El Paso", "TX", 678815),
    ("Abilene", "TX", 124177), ("Beaumont", "TX", 118228), ("Pasadena", "TX", 154000),
    ("Galveston", "TX", 52230), ("San Marcos", "TX", 67000), ("Round Rock", "TX", 128355),
    ("Cedar Park", "TX", 79040), ("Georgetown", "TX", 72954), ("Tyler", "TX", 105995),
    ("Wichita Falls", "TX", 103390), ("Brownsville", "TX", 182781), ("Grand Prairie", "TX", 196100),
    ("Shreveport", "LA", 187593), ("New Orleans", "LA", 383997), ("Baton Rouge", "LA", 225374),
    ("Metairie", "LA", 141128), ("Lafayette", "LA", 126185), ("Lake Charles", "LA", 77656),
    ("Jackson", "MS", 166965), ("Gulfport", "MS", 71012), ("Southaven", "MS", 55069),
    ("Biloxi", "MS", 46319), ("Hattiesburg", "MS", 46072), ("Little Rock", "AR", 197992),
    ("Fort Smith", "AR", 87650), ("Fayetteville", "AR", 93949), ("Springdale", "AR", 83875),
    ("Jonesboro", "AR", 78576), ("North Little Rock", "AR", 65397),
    ("Nashville", "TN", 689447), ("Memphis", "TN", 650910), ("Knoxville", "TN", 187347),
    ("Chattanooga", "TN", 180557), ("Clarksville", "TN", 166722), ("Murfreesboro", "TN", 152769),
    ("Birmingham", "AL", 215006), ("Huntsville", "AL", 215006), ("Montgomery", "AL", 199518),
    ("Mobile", "AL", 187041), ("Tuscaloosa", "AL", 100618), ("Hoover", "AL", 89435),
    ("Atlanta", "GA", 498715), ("Augusta", "GA", 202081), ("Columbus", "GA", 201840),
    ("Macon", "GA", 153159), ("Savannah", "GA", 144352), ("Athens", "GA", 126913),
    ("Roswell", "GA", 94034), ("Sandy Springs", "GA", 108080), ("Warner Robins", "GA", 80308),
    ("Columbia", "SC", 136362), ("Charleston", "SC", 150227), ("North Charleston", "SC", 113961),
    ("Greenville", "SC", 70635), ("Rock Hill", "SC", 74372), ("Mount Pleasant", "SC", 89078),
    ("Charlotte", "NC", 885708), ("Raleigh", "NC", 469298), ("Greensboro", "NC", 299035),
    ("Durham", "NC", 278993), ("Winston-Salem", "NC", 249545), ("Fayetteville", "NC", 211657),
    ("Cary", "NC", 170282), ("Wilmington", "NC", 123784), ("High Point", "NC", 114059),
    ("Asheville", "NC", 94589), ("Jacksonville", "NC", 70145), ("Chapel Hill", "NC", 61960),
    ("Richmond", "VA", 226610), ("Virginia Beach", "VA", 459470), ("Norfolk", "VA", 244703),
    ("Chesapeake", "VA", 244835), ("Newport News", "VA", 183412), ("Hampton", "VA", 137436),
    ("Alexandria", "VA", 159299), ("Roanoke", "VA", 99143),
    ("Washington", "DC", 705749),
    ("Baltimore", "MD", 585708), ("Frederick", "MD", 78171), ("Rockville", "MD", 68636),
    ("Gaithersburg", "MD", 68745),
    ("Philadelphia", "PA", 1584064), ("Pittsburgh", "PA", 300286), ("Allentown", "PA", 125845),
    ("Erie", "PA", 94831), ("Reading", "PA", 95112), ("Scranton", "PA", 76997),
    ("Newark", "NJ", 282011), ("Jersey City", "NJ", 292449), ("Paterson", "NJ", 145233),
    ("Elizabeth", "NJ", 132790), ("Trenton", "NJ", 83203),
    ("New York", "NY", 8336817), ("Buffalo", "NY", 255805), ("Rochester", "NY", 208046),
    ("Yonkers", "NY", 200810), ("Syracuse", "NY", 142553), ("Albany", "NY", 97856),
    ("Boston", "MA", 692600), ("Worcester", "MA", 185877), ("Springfield", "MA", 153677),
    ("Lowell", "MA", 115554), ("Cambridge", "MA", 117000), ("New Bedford", "MA", 95072),
    ("Brockton", "MA", 94089), ("Quincy", "MA", 94470), ("Lynn", "MA", 94299),
    ("Providence", "RI", 178042), ("Cranston", "RI", 80566), ("Warwick", "RI", 80820),
    ("Pawtucket", "RI", 71148),
    ("Hartford", "CT", 122587), ("New Haven", "CT", 130250), ("Stamford", "CT", 135470),
    ("Bridgeport", "CT", 145014), ("Waterbury", "CT", 115340),
    ("Manchester", "NH", 115644), ("Nashua", "NH", 89246), ("Concord", "NH", 43976),
    ("Portland", "ME", 68408), ("Lewiston", "ME", 36299), ("Bangor", "ME", 32029),
    ("Burlington", "VT", 45012),
    ("Portland", "OR", 652503), ("Eugene", "OR", 172622), ("Salem", "OR", 175535),
    ("Gresham", "OR", 114247), ("Hillsboro", "OR", 108661), ("Beaverton", "OR", 97590),
    ("Medford", "OR", 82895), ("Bend", "OR", 99178), ("Springfield", "OR", 62291),
    ("Seattle", "WA", 737255), ("Spokane", "WA", 222081), ("Tacoma", "WA", 217827),
    ("Vancouver", "WA", 190209), ("Bellevue", "WA", 145300), ("Kirkland", "WA", 92175),
    ("Renton", "WA", 106785), ("Redmond", "WA", 65359), ("Everett", "WA", 112024),
    ("Kent", "WA", 136588), ("Bellingham", "WA", 93074), ("Olympia", "WA", 53500),
    ("Yakima", "WA", 96968), ("Kennewick", "WA", 82037),
    ("Anchorage", "AK", 288000), ("Fairbanks", "AK", 31516), ("Juneau", "AK", 32427),
    ("Honolulu", "HI", 350395), ("Pearl City", "HI", 47698), ("Hilo", "HI", 44186),
    ("Kailua", "HI", 38635), ("Waipahu", "HI", 38216), ("Lahaina", "HI", 12702),
    ("Kahului", "HI", 26337), ("Wailuku", "HI", 16520),
    ("San Francisco", "CA", 873965), ("Los Angeles", "CA", 3979576), ("San Diego", "CA", 1423851),
    ("San Jose", "CA", 1021795), ("Fresno", "CA", 530093), ("Sacramento", "CA", 513624),
    ("Long Beach", "CA", 462628), ("Oakland", "CA", 440646), ("Bakersfield", "CA", 383579),
    ("Anaheim", "CA", 346997), ("Riverside", "CA", 330063), ("Stockton", "CA", 311034),
    ("Santa Ana", "CA", 332725), ("Chula Vista", "CA", 274492), ("Fremont", "CA", 230504),
    ("Irvine", "CA", 307670), ("San Bernardino", "CA", 215941), ("Modesto", "CA", 218464),
    ("Fontana", "CA", 214547), ("Moreno Valley", "CA", 213055), ("Glendale", "CA", 201020),
    ("Huntington Beach", "CA", 198711), ("Santa Clarita", "CA", 228673), ("Garden Grove", "CA", 171949),
    ("Oceanside", "CA", 167148), ("Rancho Cucamonga", "CA", 177751), ("Ontario", "CA", 175265),
    ("Elk Grove", "CA", 176124), ("Lancaster", "CA", 173516), ("Palmdale", "CA", 169450),
    ("Salinas", "CA", 163542), ("Hayward", "CA", 162954), ("Pomona", "CA", 151348),
    ("Visalia", "CA", 141384), ("Sunnyvale", "CA", 152258), ("Escondido", "CA", 151038),
    ("Pasadena", "CA", 141029), ("Fullerton", "CA", 143617), ("Orange", "CA", 140293),
    ("Roseville", "CA", 141500), ("Torrance", "CA", 142447), ("Corona", "CA", 169868),
    ("Berkeley", "CA", 120463), ("Santa Rosa", "CA", 175155), ("Antioch", "CA", 115006),
    ("Concord", "CA", 129295), ("Vallejo", "CA", 122880), ("Victorville", "CA", 134810),
    ("Thousand Oaks", "CA", 128731), ("Oxnard", "CA", 202063), ("Ventura", "CA", 110763),
    ("El Monte", "CA", 116853), ("Santa Barbara", "CA", 91930), ("Inglewood", "CA", 109673),
    ("Costa Mesa", "CA", 113825), ("Richmond", "CA", 110000), ("San Buenaventura", "CA", 110763),
    ("Daly City", "CA", 107007), ("Downey", "CA", 113242), ("West Covina", "CA", 107440),
    ("Santa Clara", "CA", 130365), ("El Cajon", "CA", 105061), ("Norwalk", "CA", 105195),
    ("Burbank", "CA", 105477), ("Murrieta", "CA", 116799), ("Temecula", "CA", 113808),
    ("Clovis", "CA", 120124), ("Surprise", "AZ", 148553), ("San Mateo", "CA", 103536),
    ("West Sacramento", "CA", 57100), ("Petaluma", "CA", 62703), ("Santa Cruz", "CA", 63690),
    ("Napa", "CA", 81277), ("Hemet", "CA", 90879), ("Chico", "CA", 103828),
    ("Redding", "CA", 92665), ("Livermore", "CA", 94560), ("San Leandro", "CA", 89762),
    ("Compton", "CA", 97195), ("Jurupa Valley", "CA", 106810), ("Lakewood", "CA", 79977),
    ("Hawthorne", "CA", 88083), ("Whittier", "CA", 85331), ("Alhambra", "CA", 83089),
    ("Rialto", "CA", 103526), ("Carmel", "CA", 3220), ("Monterey", "CA", 31000),
    ("Pacific Grove", "CA", 15341), ("Half Moon Bay", "CA", 12000), ("Sausalito", "CA", 7061),
    ("Mill Valley", "CA", 14994), ("Tiburon", "CA", 9100), ("San Rafael", "CA", 60177),
    ("Novato", "CA", 55787), ("Walnut Creek", "CA", 70173), ("Pleasanton", "CA", 82988),
    ("Dublin", "CA", 72589), ("Fremont", "CA", 230504), ("Union City", "CA", 75990),
    ("Newark", "CA", 48024), ("Milpitas", "CA", 80273), ("Mountain View", "CA", 82739),
    ("Palo Alto", "CA", 66666), ("Redwood City", "CA", 84481), ("San Carlos", "CA", 30721),
    ("Burlingame", "CA", 31569), ("Millbrae", "CA", 23065), ("South San Francisco", "CA", 67271),
    ("Marin", "CA", 12000), ("Sonoma", "CA", 11100), ("Healdsburg", "CA", 11979),
    ("Guerneville", "CA", 4819), ("Bodega Bay", "CA", 1077),
]


def from_csv(csv_path: Path) -> list[tuple[str, str, int]]:
    cities = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                pop = int(float(row.get("population") or row.get("pop") or 0))
            except (ValueError, TypeError):
                pop = 0
            if pop < _MIN_POP:
                continue
            city = row.get("city") or row.get("city_ascii") or ""
            state = row.get("state_id") or row.get("state_abbr") or ""
            if city and state:
                cities.append((city, state.upper(), pop))
    return cities


def build_city_list(source: list[tuple[str, str, int]]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for city, state, _pop in sorted(source, key=lambda x: -x[2]):
        key = f"{city}, {state}"
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


def main() -> None:
    if _CSV_PATH.exists():
        print(f"Reading {_CSV_PATH} …")
        source = from_csv(_CSV_PATH)
        print(f"  Loaded {len(source)} cities from CSV (pop > {_MIN_POP:,})")
    else:
        print(f"{_CSV_PATH} not found — using built-in curated list ({len(_BUILTIN_CITIES)} cities).")
        source = _BUILTIN_CITIES

    cities = build_city_list(source)
    _OUT_PATH.write_text(json.dumps(cities, indent=None, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Written {len(cities)} cities → {_OUT_PATH}  ({os.path.getsize(_OUT_PATH):,} bytes)")


if __name__ == "__main__":
    main()
