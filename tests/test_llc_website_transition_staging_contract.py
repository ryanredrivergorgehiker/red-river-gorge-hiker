from html import unescape
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def visible(path: str) -> str:
    return unescape(read(path))


class LlcWebsiteTransitionStagingContract(unittest.TestCase):
    def test_footer_exact_operator_credit(self):
        text = read("src/components/Footer.astro")
        self.assertIn("<strong>© Red River Gorge Hiker LLC.</strong>", text)
        self.assertIn("<span>All rights reserved. Photographs © Ryan D. Lewis.</span>", text)
        self.assertNotIn("Operated by Red River Gorge Hiker LLC.", text)
        self.assertNotIn("<span>© Red River Gorge Hiker LLC. All rights reserved. Photographs © Ryan D. Lewis.</span>", text)
        self.assertNotIn("<span>© Ryan D. Lewis. All rights reserved.</span>", text)
        self.assertIn('href="mailto:Ryan@RedRiverGorgeHiker.com"', text)
        self.assertIn("Analytics choices", text)
        self.assertIn("instagram", text)
        self.assertIn("facebook", text)
        self.assertIn("pinterest", text)

    def test_website_schema_uses_llc_but_photo_schema_does_not(self):
        base = read("src/layouts/Base.astro")
        photo = read("src/pages/photographs/[slug].astro")
        self.assertIn("copyrightHolder: { '@type': 'Organization', name: 'Red River Gorge Hiker LLC' }", base)
        self.assertIn("publisher: { '@type': 'Organization', name: 'Red River Gorge Hiker LLC' }", base)
        self.assertIn("creator: { '@type': 'Person', name: 'Ryan D. Lewis' }", photo)
        self.assertIn("copyrightHolder: { '@type': 'Person', name: 'Ryan D. Lewis' }", photo)
        self.assertIn("Photographs © Ryan D. Lewis. All rights reserved.", photo)
        self.assertNotIn("Red River Gorge Hiker LLC", photo)

    def test_copyright_and_terms_exact_llc_language(self):
        text = visible("src/pages/copyright-and-terms.astro")
        required = [
            "RedRiverGorgeHiker.com is operated by Red River Gorge Hiker LLC under the Red River Gorge Hiker brand. Ryan D. Lewis is the photographer behind the original Red River Gorge Hiker photography and personally retains the copyrights in his photographs.",
            "Photographs displayed on RedRiverGorgeHiker.com that are identified as photography by Ryan D. Lewis are copyrighted and owned by Ryan D. Lewis unless expressly stated otherwise. Formation and operation of Red River Gorge Hiker LLC does not transfer ownership of those photograph copyrights to the LLC.",
            "The Red River Gorge Hiker website, its written material, graphics, branding elements, layouts, and other content may also be protected by copyright, trademark, or other applicable intellectual-property laws. Nothing on this website should be interpreted as granting a license to copy, reproduce, publish, sell, adapt, distribute, display, or otherwise reuse protected material except as expressly permitted in writing or as independently allowed by applicable law.",
            "© Red River Gorge Hiker LLC. All rights reserved. Photographs © Ryan D. Lewis. All rights reserved.",
            "You are welcome to view the site and share links to its public pages. Copying, reproducing, publishing, selling, adapting, distributing, displaying, or otherwise reusing photographs or other protected material requires prior written permission unless applicable law independently permits the use.",
            "Purchasing a print, puzzle, gear item, greeting card, or other physical product does not transfer copyright, reproduction rights, or any other intellectual-property rights in the underlying photograph, artwork, branding, or other protected material.",
            "Red River Gorge Hiker LLC, operating under the Red River Gorge Hiker brand, makes no representation or warranty that any location shown or discussed on the website is currently accessible, publicly accessible, safe, accurately described, or suitable for any particular visitor.",
            "To the fullest extent permitted by applicable law, Red River Gorge Hiker LLC shall not be responsible for injuries, losses, damages, expenses, or other consequences arising from a visitor's use of or reliance upon outdoor, geographic, historical, safety, access, or location-related information provided through this website.",
            "Red River Gorge Hiker LLC, operating under the Red River Gorge Hiker brand, independently supports Wolfe County Search & Rescue through the RRGH business-support program described on this website. This is separate from Ryan D. Lewis's personal support of Wolfe County Search & Rescue. No formal partnership, sponsorship, endorsement, agency relationship, promotional arrangement, or commercial relationship with Wolfe County Search & Rescue is stated or implied. Neither Red River Gorge Hiker LLC nor Ryan D. Lewis speaks for Wolfe County Search & Rescue.",
            "Links inviting visitors to donate directly to Wolfe County Search & Rescue send visitors to WCSART's own public donation system. Direct charitable donations do not pass through Red River Gorge Hiker LLC or Ryan D. Lewis, and neither Red River Gorge Hiker LLC nor Ryan D. Lewis processes, holds, or relays those direct donations.",
            "Online print, puzzle, gear, and other product purchases linked from Red River Gorge Hiker are currently completed through Fine Art America or another specifically identified third-party provider. Those providers control their own checkout processes, payment processing, production, shipping, returns, product availability, applicable pricing, terms, and privacy practices. Red River Gorge Hiker LLC does not manufacture, ship, process payment for, or administer returns for Fine Art America orders unless a page expressly states otherwise.",
            "To the fullest extent permitted by applicable law, Red River Gorge Hiker LLC shall not be liable for any indirect, incidental, special, consequential, exemplary, or punitive damages arising from or related to access to, use of, inability to use, or reliance upon RedRiverGorgeHiker.com or its content.",
            "Nothing in these Terms is intended to exclude or limit liability that cannot lawfully be excluded or limited.",
        ]
        for item in required:
            self.assertIn(item, text)
        self.assertNotIn("all photographs, written content, graphics, and other original material displayed on RedRiverGorgeHiker.com are copyrighted and owned by Ryan D. Lewis", text)

    def test_privacy_staging_copy_and_date(self):
        text = read("src/pages/privacy.astro")
        self.assertIn("Last updated: August 19, 2026", text)
        self.assertIn("RedRiverGorgeHiker.com is operated by Red River Gorge Hiker LLC under the Red River Gorge Hiker brand. It is a static photography and outdoor-interest website. It does not create visitor accounts, run its own online shopping cart, or directly collect payment-card information.", text)
        self.assertIn("GitHub Pages and ordinary internet infrastructure may process standard technical information needed to deliver and secure the site. Optional measurement tools are described below.", text)
        self.assertIn("If you email Ryan at Ryan@RedRiverGorgeHiker.com, the information you choose to provide may be retained by Red River Gorge Hiker LLC when reasonably useful for responding to your message, administering the business, or maintaining ordinary business records.", text)
        self.assertIn("Privacy questions may be sent to Ryan@RedRiverGorgeHiker.com.", text)
        self.assertIn("Analytics storage is denied by default.", text)
        self.assertIn("Google Analytics and Pinterest measurement are configured as optional.", text)

    def test_about_contact_and_permissions_exact_copy(self):
        about = read("src/pages/about.astro")
        contact = read("src/pages/contact.astro")
        permissions = read("src/pages/photography-use-and-permissions.astro")
        self.assertIn("Red River Gorge Hiker is operated by Red River Gorge Hiker LLC.", about)
        self.assertIn("Red River Gorge Hiker was founded by <strong>Ryan D. Lewis</strong>, a photographer, hiker, backpacker, and backcountry explorer", about)
        self.assertIn("Red River Gorge Hiker is operated by Red River Gorge Hiker LLC. Ryan D. Lewis remains the photographer and the contact for photography, image-use, and general Red River Gorge Hiker inquiries.", contact)
        self.assertIn("Ryan@RedRiverGorgeHiker.com", contact)
        self.assertIn("Fine Art America orders", contact)
        self.assertIn("Photographs on Red River Gorge Hiker are copyrighted by Ryan D. Lewis.", permissions)
        self.assertIn("Red River Gorge Hiker LLC operates the Red River Gorge Hiker website and business, but ownership of Ryan D. Lewis's photograph copyrights remains with Ryan D. Lewis.", permissions)
        self.assertIn("Permission is only granted when Ryan confirms it in writing.", permissions)
        self.assertIn("Ryan@RedRiverGorgeHiker.com", permissions)

    def test_sar_business_personal_split_without_financial_logic_changes(self):
        text = visible("src/pages/search-and-rescue.astro")
        self.assertIn("20% of RRGH business profit is allocated to Wolfe County Search & Rescue.", text)
        self.assertIn("When Red River Gorge Hiker launched, Ryan decided the business itself should give back too. Following formation of Red River Gorge Hiker LLC, the RRGH business-support commitment continues through the LLC. Separately from that business commitment, Ryan D. Lewis maintains his own personal support of Wolfe County Search & Rescue. Twenty percent of RRGH business profit is allocated to Wolfe County Search & Rescue.", text)
        self.assertIn("Red River Gorge Hiker LLC supports Wolfe County Search & Rescue independently through the Red River Gorge Hiker business-support program. Ryan D. Lewis's personal support is separate. This is not a partnership, sponsorship, endorsement, agency relationship, or commercial arrangement, and Red River Gorge Hiker LLC does not speak on WCSART's behalf.", text)
        for invariant in [
            "sar.personalAnnualCommitment",
            "sar.rrghSarGenerated",
            "sar.rrghSarDonated",
            "sar.outstandingCommitment",
            "sar.annualCombinedSupport",
            "sar.historicalPersonalSupport",
            "sar.lifetimePersonalSupport",
            "sar.lifetimeRrghSupport",
            "sar.lifetimeRrghTransferred",
            "sar.combinedLifetimeSupport",
            "sar.matchPercentage",
            "sar.lastUpdated",
        ]:
            self.assertIn(invariant, text)

    def test_six_photo_catalog_and_artwork_component_remain_llc_free(self):
        products = read("src/data/products.ts")
        artwork = read("src/components/Artwork.astro")
        for title in [
            "Double Rainbow at Eagle’s Point Buttress",
            "Winter at Red-byrd Arch",
            "Sunrise at Eagle’s Nest",
            "Dog Fork Falls in Winter",
            "Ice at West of Copperas Pillar",
            "Splatter Falls",
        ]:
            self.assertIn(title, products)
        self.assertNotIn("Red River Gorge Hiker LLC", products)
        self.assertNotIn("Red River Gorge Hiker LLC", artwork)


if __name__ == "__main__":
    unittest.main()
