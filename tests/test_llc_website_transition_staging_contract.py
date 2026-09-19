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
        self.assertIn("<strong>© Red River Gorge Hiker, LLC. All rights reserved.</strong>", text)
        self.assertNotIn("Photographs © Ryan D. Lewis.", text)
        self.assertNotIn("Operated by Red River Gorge Hiker, LLC.", text)
        self.assertNotIn("<span>© Red River Gorge Hiker, LLC. All rights reserved. Photographs © Ryan D. Lewis.</span>", text)
        self.assertNotIn("<span>© Ryan D. Lewis. All rights reserved.</span>", text)
        self.assertIn('href="mailto:Info@RedRiverGorgeHiker.com"', text)
        self.assertIn("Privacy & Analytics", text)
        self.assertIn("privacy/#privacy-and-analytics", text)
        self.assertNotIn("Analytics choices", text)
        self.assertIn("instagram", text)
        self.assertIn("facebook", text)
        self.assertIn("pinterest", text)

    def test_website_schema_uses_llc_but_photo_schema_does_not(self):
        base = read("src/layouts/Base.astro")
        photo = read("src/pages/photographs/[slug].astro")
        self.assertIn("copyrightHolder: { '@type': 'Organization', name: 'Red River Gorge Hiker, LLC' }", base)
        self.assertIn("publisher: { '@type': 'Organization', name: 'Red River Gorge Hiker, LLC' }", base)
        self.assertIn("creator: { '@type': 'Person', name: photo.creatorName }", photo)
        self.assertIn("copyrightHolder: { '@type': 'Person', name: photo.copyrightHolder }", photo)
        self.assertIn("Photograph {photo.copyrightNotice}", photo)
        self.assertNotIn("Photograph © Ryan D. Lewis. All rights reserved.", photo)
        self.assertNotIn("Red River Gorge Hiker, LLC", photo)

    def test_copyright_and_terms_exact_llc_language(self):
        text = visible("src/pages/copyright-and-terms.astro")
        required = [
            "RedRiverGorgeHiker.com is operated by Red River Gorge Hiker, LLC under the Red River Gorge Hiker brand. Ryan D. Lewis is the photographer behind the original Red River Gorge Hiker photography and personally retains the copyrights in his photographs.",
            "Photographs displayed on RedRiverGorgeHiker.com that are identified as photography by Ryan D. Lewis are copyrighted and owned by Ryan D. Lewis unless expressly stated otherwise. Formation and operation of Red River Gorge Hiker, LLC does not transfer ownership of those photograph copyrights to the LLC.",
            "The Red River Gorge Hiker website, its written material, graphics, branding elements, layouts, and other content may also be protected by copyright, trademark, or other applicable intellectual-property laws. Nothing on this website should be interpreted as granting a license to copy, reproduce, publish, sell, adapt, distribute, display, or otherwise reuse protected material except as expressly permitted in writing or as independently allowed by applicable law.",
            "© Red River Gorge Hiker, LLC. All rights reserved. Creator-specific copyright notices are identified with the applicable work.",
            "You are welcome to view the site and share links to its public pages. Copying, reproducing, publishing, selling, adapting, distributing, displaying, or otherwise reusing photographs or other protected material requires prior written permission unless applicable law independently permits the use.",
            "Purchasing a print, puzzle, gear item, greeting card, or other physical product does not transfer copyright, reproduction rights, or any other intellectual-property rights in the underlying photograph, artwork, branding, or other protected material.",
            "Red River Gorge Hiker, LLC, operating under the Red River Gorge Hiker brand, makes no representation or warranty that any location shown or discussed on the website is currently accessible, publicly accessible, safe, accurately described, or suitable for any particular visitor.",
            "To the fullest extent permitted by applicable law, Red River Gorge Hiker, LLC shall not be responsible for injuries, losses, damages, expenses, or other consequences arising from a visitor's use of or reliance upon outdoor, geographic, historical, safety, access, or location-related information provided through this website.",
            "Red River Gorge Hiker, LLC independently supports Wolfe County Search & Rescue. RRGH maintains a minimum $500 annual Company commitment and separately allocates 20% of positive Red River Gorge Hiker business profit. These commitments are separate and additive; neither offsets or satisfies the other. Historical personal support by Ryan D. Lewis remains separate from Company support.",
            "Links inviting visitors to donate directly to Wolfe County Search & Rescue send visitors to WCSART's own public donation system. Direct charitable donations do not pass through Red River Gorge Hiker, LLC or Ryan D. Lewis, and neither Red River Gorge Hiker, LLC nor Ryan D. Lewis processes, holds, or relays those direct donations.",
            "Online product purchases linked from Red River Gorge Hiker are completed through the Red River Gorge Hiker Store at store.RedRiverGorgeHiker.com, which is powered by Pixels / Fine Art America. Pixels operates the checkout and payment system and handles on-demand production, shipping, customer service, and returns. Purchases through the Store are also subject to the applicable Pixels terms, privacy practices, and return policies. Red River Gorge Hiker, LLC does not manufacture or ship Pixels orders, process buyers’ payment cards, or administer Pixels returns.",
            "To the fullest extent permitted by applicable law, Red River Gorge Hiker, LLC shall not be liable for any indirect, incidental, special, consequential, exemplary, or punitive damages arising from or related to access to, use of, inability to use, or reliance upon RedRiverGorgeHiker.com or its content.",
            "Nothing in these Terms is intended to exclude or limit liability that cannot lawfully be excluded or limited.",
        ]
        for item in required:
            self.assertIn(item, text)
        self.assertNotIn("all photographs, written content, graphics, and other original material displayed on RedRiverGorgeHiker.com are copyrighted and owned by Ryan D. Lewis", text)

    def test_privacy_production_ready_copy_and_date(self):
        text = read("src/pages/privacy.astro")
        self.assertIn("Last updated: September 17, 2026", text)
        self.assertNotIn("Last updated: Pending production approval", text)
        self.assertIn("RedRiverGorgeHiker.com is operated by Red River Gorge Hiker, LLC under the Red River Gorge Hiker brand. It is a static photography and outdoor-interest website. It does not create visitor accounts, run its own online shopping cart, or directly collect payment-card information.", text)
        self.assertIn("GitHub Pages and ordinary internet infrastructure may process standard technical information needed to deliver and secure the site. Red River Gorge Hiker measurement tools are described below.", text)
        self.assertIn("If you email Red River Gorge Hiker at Info@RedRiverGorgeHiker.com, the information you choose to provide may be retained by Red River Gorge Hiker, LLC when reasonably useful for responding to your message, administering the business, or maintaining ordinary business records.", text)
        self.assertIn("Privacy questions may be sent to Info@RedRiverGorgeHiker.com.", text)
        self.assertIn("RRGH Analytics may be On by default", text)
        self.assertIn("RRGH Analytics remains Off until the visitor affirmatively turns it On", text)
        self.assertIn("Pixels platform analytics operates independently from RRGH Analytics", text)
        self.assertIn("does not enable Pinterest Enhanced Match", text)

    def test_about_contact_and_permissions_exact_copy(self):
        about = read("src/pages/about.astro")
        contact = read("src/pages/contact.astro")
        permissions = read("src/pages/photography-use-and-permissions.astro")
        self.assertIn("Red River Gorge Hiker is operated by Red River Gorge Hiker, LLC.", about)
        self.assertIn("Red River Gorge Hiker grew from years spent hiking, backpacking, photographing, and exploring", about)
        self.assertIn("General public inquiries are handled through the brand’s information address.", contact)
        self.assertIn("Info@RedRiverGorgeHiker.com", contact)
        self.assertIn("Store orders", contact)
        self.assertIn("Current photographs identified as photography by Ryan D. Lewis remain copyrighted by Ryan D. Lewis", permissions)
        self.assertIn("the website does not transfer those copyrights to the LLC", permissions)
        self.assertIn("Permission must be granted in writing by the applicable copyright holder or authorized rights representative.", permissions)
        self.assertIn("Info@RedRiverGorgeHiker.com", permissions)

    def test_sar_leg_dec_0027_company_commitment_contract(self):
        text = visible("src/pages/search-and-rescue.astro")
        data = read("src/data/sar.ts")
        self.assertIn("Red River Gorge Hiker, LLC maintains two separate commitments to Wolfe County Search & Rescue: at least $500 each calendar year, plus 20% of positive Red River Gorge Hiker business profit.", text)
        self.assertIn("Neither commitment offsets or satisfies the other.", text)
        self.assertIn("Historical personal support before the RRGH program", text)
        for invariant in [
            "sar.rrghAnnualBaseCommitment",
            "sar.rrghProfitAllocationGenerated",
            "sar.rrghTotalCommitment",
            "sar.rrghBaseCommitmentTransferred",
            "sar.rrghProfitAllocationTransferred",
            "sar.rrghTotalTransferred",
            "sar.outstandingBaseCommitment",
            "sar.outstandingProfitAllocation",
            "sar.outstandingRrghCommitment",
            "sar.commitmentFulfillmentPercentage",
            "sar.historicalPersonalSupport",
            "sar.lifetimePersonalSupport",
            "sar.lifetimeRrghCommitted",
            "sar.lifetimeRrghTransferred",
            "sar.combinedLifetimeSupport",
            "sar.lastUpdated",
        ]:
            self.assertIn(invariant, text)
        for legacy in [
            "personalAnnualCommitment",
            "rrghSarGenerated",
            "rrghSarDonated",
            "outstandingCommitment",
            "matchPercentage",
            "annualCombinedSupport",
            "lifetimeRrghSupport",
        ]:
            self.assertNotIn(legacy, data)
            self.assertNotIn(f"sar.{legacy}", text)

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
        self.assertNotIn("Red River Gorge Hiker, LLC", products)
        self.assertNotIn("Red River Gorge Hiker, LLC", artwork)


if __name__ == "__main__":
    unittest.main()
