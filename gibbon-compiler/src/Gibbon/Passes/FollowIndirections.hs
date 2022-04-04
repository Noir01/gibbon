module Gibbon.Passes.FollowIndirections
  ( followIndirections )
  where

import qualified Data.Map as M
-- import qualified Data.Set as S
import qualified Data.List as L
-- import           Data.Foldable ( foldrM )
import           Data.Maybe ( fromJust )

import           Gibbon.Common
import           Gibbon.Language
import           Gibbon.L2.Syntax as L2

--------------------------------------------------------------------------------

followIndirections :: Prog2 -> PassM Prog2
followIndirections (Prog ddefs fundefs mainExp) = do
    fds' <- mapM gofun (M.elems fundefs)
    let fundefs' = M.fromList $ map (\f -> (funName f,f)) fds'
    pure $ Prog ddefs fundefs' mainExp
  where
    gofun :: FunDef2 -> PassM FunDef2
    gofun f@FunDef{funName,funArgs,funBody,funTy} = do
      let in_tys = arrIns funTy
      let out_ty = arrOut funTy
      funBody' <-
        case funBody of
          CaseE scrt brs -> do
            let VarE scrtv = scrt
                PackedTy tycon scrt_loc = snd $ fromJust $ L.find (\t -> fst t == scrtv) (zip funArgs in_tys)
                DDef{dataCons} = lookupDDef ddefs tycon

            indir_ptrv <- gensym "indr"
            indir_ptrloc <- gensym "case"
            jump <- gensym "jump"
            callv <- gensym "call"
            let _effs = arrEffs funTy
            endofs <- mapM (\_ -> gensym "endof") (locRets funTy)
            let ret_endofs = foldr (\(end, (EndOf (LRM loc _ _))) acc ->
                                      if loc == scrt_loc
                                      then jump : acc
                                      else end : acc)
                             []
                             (zip endofs (locRets funTy))
            let args = foldr (\v acc -> if v == scrtv
                                        then ((VarE indir_ptrv) : acc)
                                        else (VarE v : acc))
                             [] funArgs
            let in_locs = foldr (\loc acc -> if loc ==  scrt_loc then (indir_ptrv : acc) else (loc : acc)) [] (inLocVars funTy)
            let out_locs = outLocVars funTy
            wc <- gensym "wildcard"
            let indir_bod = Ext $ LetLocE jump (AfterConstantLE 8 indir_ptrloc) $
                            (if isPrinterName funName then LetE (wc,[],ProdTy[],PrimAppE PrintSym [LitSymE (toVar " ->i ")]) else id) $
                            LetE (callv,endofs,out_ty,AppE funName (in_locs ++ out_locs) args) $
                            Ext (RetE ret_endofs callv)
            let indir_dcon = fst $ fromJust $ L.find (isIndirectionTag . fst) dataCons
            let indir_br = (indir_dcon,[(indir_ptrv,indir_ptrloc)],indir_bod)
            ----------------------------------------
            let redir_dcon = fst $ fromJust $ L.find (isRedirectionTag . fst) dataCons
            let redir_bod = (if isPrinterName funName then LetE (wc,[],ProdTy[],PrimAppE PrintSym [LitSymE (toVar " ->r ")]) else id) $
                            LetE (callv,endofs,out_ty,AppE funName (in_locs ++ out_locs) args) $
                            Ext (RetE endofs callv)
            let redir_br = (redir_dcon,[(indir_ptrv,indir_ptrloc)],redir_bod)
            ----------------------------------------
            (pure (CaseE scrt (brs ++ [indir_br,redir_br])))
          _ -> pure funBody
      pure $ f { funBody = funBody' }
