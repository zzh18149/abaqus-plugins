        subroutine vumat(
c     Read only -
     1 nblock, ndir, nshr, nstatev, nfieldv, nprops, lanneal,
     2 stepTime, totalTime, dt, cmname, coordMp, charLength,
     3 props, density, strainInc, relSpinInc,
     4 tempOld, stretchOld, defgradOld, fieldOld,
     5 stressOld, stateOld, enerInternOld, enerInelasOld,
     6 tempNew, stretchNew, defgradNew, fieldNew,
c     Write only -
     7 stressNew, stateNew, enerInternNew, enerInelasNew )
c
      include 'vaba_param.inc'
c
      dimension props(nprops), density(nblock),
     1 coordMp(nblock,*),
     2 charLength(nblock), strainInc(nblock,ndir+nshr),
     3 relSpinInc(nblock,nshr), tempOld(nblock),
     4 stretchOld(nblock,ndir+nshr), defgradOld(nblock,ndir+nshr+nshr),
     5 fieldOld(nblock,nfieldv), stressOld(nblock,ndir+nshr),
     6 stateOld(nblock,nstatev), enerInternOld(nblock),
     7 enerInelasOld(nblock), tempNew(nblock),
     8 stretchNew(nblock,ndir+nshr), defgradNew(nblock,ndir+nshr+nshr),
     9 fieldNew(nblock,nfieldv), stressNew(nblock,ndir+nshr),
     1 stateNew(nblock,nstatev),
     2 enerInternNew(nblock), enerInelasNew(nblock)
c
      character*80 cmname
      parameter( zero = 0.d0, one = 1.d0, two = 2.d0, half = .5d0 )
      parameter( eMax = .80d0, eMin = -.80d0,RSR=1.d-3 )
      parameter(
     *          i_Xx = 1,
     *          i_Yy = 2,
     *          i_Zz = 3,
     *          i_Xy = 4,
     *          i_Yz = 5,
     *          i_Zx = 6,
     *          n_v3d_Car=3 )
      parameter(
     *          i_svd_statusMp = 1,
     *          i_svd_DmgFiberT = 2,
     *          i_svd_DmgFiberC = 3,
     *          i_svd_DmgMatrixT = 4,
     *          i_svd_DmgMatrixC = 5,
     *          i_svd_DmgDelamination = 6, 
     *          i_svd_dampStress = 7,
c                 * i_svd_dampStressXx = 7,
c                 * i_svd_dampStressYy = 8,
c                 * i_svd_dampStressZz = 9,
c                 * i_svd_dampStressXy = 10,
c                 * i_svd_dampStressYz = 11,
c                 * i_svd_dampStressZx = 12,
     *          i_svd_Strain = 13,
c                 * i_svd_StrainXx = 13,
c                 * i_svd_StrainYy = 14,
c                 * i_svd_StrainZz = 15,
c                 * i_svd_StrainXy = 16,
c                 * i_svd_StrainYz = 17,
c                 * i_svd_StrainZx = 18,
     *          i_svd_min_eq_disp_ft = 19,
     *          i_svd_min_eq_disp_fc = 20,
     *          i_svd_min_eq_disp_mt = 21,
     *          i_svd_min_eq_disp_mc = 22,
     *          i_svd_min_eq_disp_dl = 23,
     *          i_svd_max_eq_disp_ft = 24,
     *          i_svd_max_eq_disp_fc = 25,
     *          i_svd_max_eq_disp_mt = 26,
     *          i_svd_max_eq_disp_mc = 27,
     *          i_svd_max_eq_disp_dl = 28,
     *          i_svd_dft = 29,
     *          i_svd_dfc = 30,
     *          i_svd_dmt = 31,
     *          i_svd_dmc = 32,
     *          i_svd_dlt = 33,     
     *          i_svd_dlc = 34,
     *          i_svd_dft_novis = 35,
     *          i_svd_dfc_novis = 36,
     *          i_svd_dmt_novis = 37,
     *          i_svd_dmc_novis = 38,
     *          i_svd_del_novis = 39,
     *          i_svd_enomMax = 40,
     *          i_svd_enomMin = 41,
     *          i_svd_dt = 42,
     *          n_svd_Required = 63 )
      parameter (
     *           i_pro_E1 = 1,
     *           i_pro_E2 = 2,
     *           i_pro_E3 = 3,
     *           i_pro_nu12 = 4,
     *           i_pro_nu13 = 5,
     *           i_pro_nu23 = 6,
     *           i_pro_G12 = 7,
     *           i_pro_G13 = 8,
     *           i_pro_G23 = 9,         
     *           i_pro_beta = 10,
     *           i_pro_alpha = 11,
     *           i_pro_gama = 12,         
     *           i_pro_sigu1t = 17,
     *           i_pro_sigu1c = 18,
     *           i_pro_sigu2t = 19,
     *           i_pro_sigu2c = 20,
     *           i_pro_sigu3t = 21,
     *           i_pro_sigu3c = 22,
     *           i_pro_sigu12 = 25,
     *           i_pro_sigu13 = 26,
     *           i_pro_sigu23 = 27,	             
     *           i_pro_feft = 33,
     *           i_pro_fefc = 34,
     *           i_pro_femt = 35,
     *           i_pro_femc = 36,
     *           i_pro_fedl = 37 )
      dimension eigen( nblock , n_v3d_Car )
c     Read material properties
        E1 = props( i_pro_E1 )
        E2 = props( i_pro_E2 )
        E3 = props( i_pro_E3 )
        xnu12 = props( i_pro_nu12 )
        xnu13 = props( i_pro_nu13 )
        xnu23 = props( i_pro_nu23 )
        G12 = props( i_pro_G12 )
        G13 = props( i_pro_G13 )
        G23 = props( i_pro_G23 )
        f1t = props( i_pro_sigu1t )
        f1c = props( i_pro_sigu1c )
        f2t = props( i_pro_sigu2t )
        f2c = props( i_pro_sigu2c )
        f3t = props( i_pro_sigu3t )
        f3c = props( i_pro_sigu3c )
        f12 = props( i_pro_sigu12 )
        f13 = props( i_pro_sigu13 )
        f23 = props( i_pro_sigu23 )
        feft = props( i_pro_feft )
        fefc = props( i_pro_fefc )
        femt = props( i_pro_femt )
        femc = props( i_pro_femc )
        fedl = props( i_pro_fedl )
        beta = props( i_pro_beta )
        alpha = props( i_pro_alpha )
        gama = props( i_pro_gama )
c
c-------------------------Strain accumulation----------------------------------------       
        do k = 1, nblock
      do j = 1, nstatev
         stateNew(k,j)=stateOld(k,j)
      end do
      if ( totalTime .eq. zero ) then
         stateNew(k,i_svd_statusMp)=one
      end if
      stateNew(k,43)=stateOld(k,43)+strainInc(k,1)
      stateNew(k,44)=stateOld(k,44)+strainInc(k,2)
      stateNew(k,45)=stateOld(k,45)+strainInc(k,3)
      stateNew(k,46)=stateOld(k,46)+strainInc(k,4)
      stateNew(k,47)=stateOld(k,47)+strainInc(k,5)
      stateNew(k,48)=stateOld(k,48)+strainInc(k,6)
C      Ӧ���ۻ�    
      stateNew(k,49)=f1t*(1.0+0.0003*
     * log(max(abs(strainInc(k,1))/dt,RSR)/RSR))
      stateNew(k,50)=f1c*(1.0+0.0003*
     * log(max(abs(strainInc(k,1))/dt,RSR)/RSR))
      stateNew(k,51)=f2t*(1.0+0.0003*
     * log(max(abs(strainInc(k,2))/dt,RSR)/RSR))
      stateNew(k,52)=f2c*(1.0+0.0003*
     * log(max(abs(strainInc(k,2))/dt,RSR)/RSR))
      stateNew(k,53)=f3t*(1.0+0.0003*
     * log(max(abs(strainInc(k,3))/dt,RSR)/RSR))
      stateNew(k,54)=f3c*(1.0+0.0003*
     * log(max(abs(strainInc(k,3))/dt,RSR)/RSR))
      stateNew(k,55)=f12*(1.0+0.0003*
     * log(max(abs(strainInc(k,4))/dt,RSR)/RSR))
      stateNew(k,56)=f23*(1.0+0.0003*
     * log(max(abs(strainInc(k,5))/dt,RSR)/RSR))
      stateNew(k,57)=f13*(1.0+0.0003*
     * log(max(abs(strainInc(k,6))/dt,RSR)/RSR))
      stateNew(k,58)=strainInc(k,1)/dt
      stateNew(k,59)=strainInc(k,2)/dt
      stateNew(k,60)=strainInc(k,3)/dt
      stateNew(k,61)=strainInc(k,4)/dt
      stateNew(k,62)=strainInc(k,5)/dt
      stateNew(k,63)=strainInc(k,6)/dt
      
C      Ӧ����ǿ��-�������     
      
        end do
        
c     Pretreatment
      if ( totalTime .eq. zero ) then
         if ( nstatev .lt. n_svd_Required ) then
            call xplb_abqerr(-2,'Subroutine VUMAT requires the '//
     *      'specification of %I state variables. Check the '//
     *      'definition of *DEPVAR in the input file.',
     *      n_svd_Required,zero,' ')
            call xplb_exit
         end if
         call OrthoEla3dExp ( 
c          read
     *       nblock,
     *       E1, E2, E3, xnu12, xnu13, xnu23, G12, G13, G23,
     *       strainInc, 
     *       stateOld( 1, i_svd_dft ), stateOld( 1, i_svd_dfc ),
     *       stateOld( 1, i_svd_dmt ), stateOld( 1, i_svd_dmc ),
     *       stateOld( 1, i_svd_dlt ), stateOld( 1, i_svd_dlc ),
c          write 
     *       stressNew )
      end if
c
c     Update total elastic strain
      call UpdateStrain ( nblock, strainInc,
     *  stateOld( 1, i_svd_strain ), stateNew( 1, i_svd_strain ) )
c
c     Stress update
      call OrthoEla3dExp ( 
c       read
     *    nblock,
     *    E1, E2, E3, xnu12, xnu13, xnu23, G12, G13, G23,
     *    stateNew( 1, i_svd_strain ),
     *    stateOld( 1, i_svd_dft ), stateOld( 1, i_svd_dfc ),
     *    stateOld( 1, i_svd_dmt ), stateOld( 1, i_svd_dmc ),
     *    stateOld( 1, i_svd_dlt ), stateOld( 1, i_svd_dlc ), 
c       write
     *    stressNew )
c    
c     Damage initiation criteria - looking for new damage  
      call Hou3d( 
c       read
     *    nblock,dt,
     *    f1t, f2t, f3t, f1c, f2c, f3c, f12, f23, f13,
     *    alpha, gama, stressNew,
     *    stateOld( 1, i_svd_DmgFiberT ),
     *    stateOld( 1, i_svd_DmgFiberC ),
     *    stateOld( 1, i_svd_DmgMatrixT ),
     *    stateOld( 1, i_svd_DmgMatrixC ),
     *    stateOld( 1, i_svd_DmgDelamination ), 
     *    stateOld( 1, i_svd_statusMp ),
     *    strainInc, 
c       write ( update )
     *    stateNew( 1, i_svd_DmgFiberT ),
     *    stateNew( 1, i_svd_DmgFiberC ),
     *    stateNew( 1, i_svd_DmgMatrixT ),
     *    stateNew( 1, i_svd_DmgMatrixC ),
     *    stateNew( 1, i_svd_DmgDelamination ),
     *    stateNew( 1, i_svd_statusMp ) )
c
c     Damage evolution
      call Murakami( 
c       read
     *    nblock, ndir, nshr, nstatev, dt, charLength,
     *    alpha, gama, stateOld, stressNew,
     *    feft, fefc, femt, femc, fedl,  
c       write 
     *    stateNew )
c
c     Apply the newly evolved damage in the same increment.  The previous
c     implementation delayed the stress degradation by one increment, which
c     generated a sharp artificial release of stored energy.
      call OrthoEla3dExp (
c       read
     *    nblock,
     *    E1, E2, E3, xnu12, xnu13, xnu23, G12, G13, G23,
     *    stateNew( 1, i_svd_strain ),
     *    stateNew( 1, i_svd_dft ), stateNew( 1, i_svd_dfc ),
     *    stateNew( 1, i_svd_dmt ), stateNew( 1, i_svd_dmc ),
     *    stateNew( 1, i_svd_dlt ), stateNew( 1, i_svd_dlc ),
c       write
     *    stressNew )
c
c     Integrate the internal specific energy (per unit mass)
      call EnergyInternal3d ( nblock, stressOld, stressNew,
     *  strainInc, density, enerInternOld, enerInternNew )
      call EnergyInelastic3d ( nblock, stressNew,
     *  stateNew( 1, i_svd_strain ), density,
     *  enerInternNew, enerInelasOld, enerInelasNew )
c
c-------------------------element deletion--------------------------
      call eig33Anal ( nblock, stretchNew, eigen )
       do k = 1, nblock       
         eigMax=max(eigen(k,i_Xx),eigen(k,i_Yy),eigen(k,i_Zz))
         eigMin=min(eigen(k,i_Xx),eigen(k,i_Yy),eigen(k,i_Zz))
         enomMax = eigMax - one 
         enomMin = eigMin - one 
         if ( enomMax .gt. eMax .or. 
     *        enomMin .lt. eMin ) then
             stateNew(k,1) = zero
         end if
c         Fully damaged material is retained with the residual stiffness
c         defined in OrthoEla3dExp.  Immediate deletion at d=0.99 discarded
c         stored energy and produced nonphysical reaction-force rebounds.
c         The principal-strain limits above are only an emergency safeguard.
		 stateNew(k,40)=enomMax
		 stateNew(k,41)=enomMin
		 stateNew(k,42)=dt
       end do
c-------------------------------------------------------------------
c
      return
        end


        subroutine OrthoEla3dExp ( 
c     read
     *  nblock, 
     *  E1, E2, E3, xnu12, xnu13, xnu23, G12, G13, G23,
     *  strain,	 
     *  dft, dfc, dmt, dmc, dlt, dlc,
c     write 
     *  stress )
c 
      include 'vaba_param.inc' 
      parameter( zero = 0.d0, one = 1.d0, two = 2.d0 )
      parameter(
     *          i_Xx = 1,
     *          i_Yy = 2,
     *          i_Zz = 3,
     *          i_Xy = 4,
     *          i_Yz = 5,
     *          i_Zx = 6, 
     *          n_Car = 6 )
c
      dimension strain( nblock, n_Car ),
     *          stress( nblock, n_Car ),
     *          dft( nblock ), dfc( nblock ), 
     *          dmt( nblock ), dmc( nblock ),
     *          dlt( nblock ), dlc( nblock )
c
c     Compute damaged stiffness
      do k = 1, nblock      
		 df = one - max ( min(dft(k),0.99d0) , min(dfc(k),0.99d0))
		 dm = one - max ( min(dmt(k),0.95d0) , min(dmc(k),0.95d0))
		 dg = one - max ( min(dlt(k),0.99d0) , min(dlc(k),0.99d0))
c
         xnu21 = xnu12 * E2 / E1
         xnu31 = xnu13 * E3 / E1
         xnu32 = xnu23 * E3 / E2
         delta = one
     1         - df * dm * xnu12 * xnu21
     2         - dm * dg * xnu23 * xnu32 
     3         - df * dg * xnu31 * xnu13
     4         - two * df * dm * dg * xnu21 * xnu32 * xnu13
         delta = one / delta
         C11 = E1 * df * ( one - dm * dg * xnu23 * xnu32 ) * delta
         C22 = E2 * dm * ( one - df * dg * xnu13 * xnu31 ) * delta
         C33 = E3 * dg * ( one - df * dm * xnu12 * xnu21 ) * delta
         C12 = E1 * df * dm * ( xnu21 + dg * xnu31 * xnu23 ) * delta
         C13 = E1 * df * dg * ( xnu31 + dm * xnu21 * xnu32 ) * delta
         C23 = E2 * dm * dg * ( xnu32 + df * xnu12 * xnu31 ) * delta
         dG12 = G12 * df * dm
         dG23 = G23 * dm * dg
         dG13 = G13 * df * dg
c     Stress update
         stress( k, i_Xx ) = C11 * strain( k, i_Xx )
     *                           + C12 * strain( k, i_Yy )
     *                           + C13 * strain( k, i_Zz )
         stress( k, i_Yy ) = C12 * strain( k,i_Xx )
     *                           + C22 * strain( k, i_Yy )
     *                           + C23 * strain( k, i_Zz )
         stress( k, i_Zz ) = C13 * strain( k, i_Xx )
     *                           + C23 * strain( k, i_Yy )
     *                           + C33 * strain( k, i_Zz )                         
         stress( k, i_Xy ) = two * dG12 * strain( k, i_Xy )
         stress( k, i_Yz ) = two * dG23 * strain( k, i_Yz )
         stress( k, i_Zx ) = two * dG13 * strain( k, i_Zx )  
      end do
c
      return
        end       


        subroutine Hou3d( 
c     read
     *  nblock,dt,
     *  f1t, f2t, f3t, f1c, f2c, f3c, f12, f23, f13,
     *  alpha, gama, stress,
     *  DmgFiberT_Old,
     *  DmgFiberC_Old,
     *  DmgMatrixT_Old,
     *  DmgMatrixC_Old,
     *  DmgDelamination_Old,
     *  statusMp_Old,
     *  strainInc,
c     write - damage state variables, zero or one
     *  DmgFiberT_New,
     *  DmgFiberC_New,
     *  DmgMatrixT_New,
     *  DmgMatrixC_New,
     *  DmgDelamination_New,
     *  statusMp_New )
c
      include 'vaba_param.inc'
      parameter( zero = 0.d0, one = 1.d0, onefourth = 0.25d0,RSR=1.d-3 )
      parameter(
     *          i_Xx = 1, i_Yy = 2, i_Zz = 3,
     *          i_Xy = 4, i_Yz = 5, i_Zx = 6,
     *          n_Car = 6 )
c
      dimension dmgFiberT_Old( nblock ), dmgFiberC_Old( nblock ),
     *          dmgMatrixT_Old( nblock ), dmgMatrixC_Old( nblock ),
     *          dmgDelamination_Old( nblock ),
     *          statusMp_Old( nblock ),     
     *          dmgFiberT_New( nblock ), dmgFiberC_New( nblock ),
     *          dmgMatrixT_New( nblock ), dmgMatrixC_New( nblock ),
     *          dmgDelamination_New( nblock ),
     *          stress( nblock, n_Car ),
     *          statusMp_New( nblock ),strainInc(nblock,n_Car)    
c
      do k = 1, nblock
c     The available material data are static strengths.  The previous
c     logarithmic rate multiplier was not calibrated and made the result
c     depend on the artificial Explicit loading rate.  Use the measured
c     static strengths for this quasi-static residual-strength analysis.
      f1tr=f1t
      f1cr=f1c
      f2tr=f2t
      f2cr=f2c
      f3tr=f3t
      f3cr=f3c
      f12r=f12
      f23r=f23
      f13r=f13
c     Active material points ( statusMp(k) .eq. one )
        if ( statusMp_Old( k ) .eq. one ) then
c
         dmgFiberT_New( k ) = dmgFiberT_Old( k ) 
         dmgFiberC_New( k ) = dmgFiberC_Old( k )
         dmgMatrixT_New( k ) = dmgMatrixT_Old( k )
         dmgMatrixC_New( k ) = dmgMatrixC_Old( k )      
         dmgDelamination_New( k ) = dmgDelamination_Old( k )
         s11 = stress( k, i_Xx )
         s22 = stress( k, i_Yy )
         s33 = stress( k, i_Zz )
         s12 = stress( k, i_Xy )
         s23 = stress( k, i_Yz )
         s13 = stress( k, i_Zx )
c     Fiber tensile failure (ft)
         if ( s11 .gt. zero ) then
            rft = ( s11 / f1tr )**2 
     *           + alpha * ( s12 / f12r )**2
     *           + alpha * ( s13 / f13r )**2
            if ( rft .ge. one ) then
               dmgFiberT_New( k ) = one
            end if
         end if
c     Fiber compression and matrix-fiber shear failure (fc)
         if ( s11 .lt. zero ) then
            rfc = ( s11 / f1cr )**2
     *           + ( s12 / f12r )**2
     *           + ( s13 / f13r )**2
            if ( rfc .gt. one ) then
               dmgFiberC_New( k ) = one
            end if
         end if
c     Matrix tensile failure (mt)*/
         if ( s22 .gt. zero ) then
            rmt = ( s22 / f2tr )**2
     *           + gama * ( s12 / f12r )**2
     *           + gama * ( s23 / f23r )**2
            if ( rmt .ge. one ) then
               dmgMatrixT_New( k ) = one
            end if
         end if
c     Matrix Crushing failure (mc)*/
         if ( s22 .lt. zero ) then
            rmc = ( s22 / f2cr )**2
     *           + ( s12 / f12r )**2
     *           + ( s23 / f23r )**2
            if ( rmc .ge. one ) then
               dmgMatrixC_New( k ) = one
            end if          
         end if
c     Tensile/compressive delamination (dl)
         if ( s33 .ge. zero ) then
            rd = ( s33 / f3tr )**2
     *          + ( s23 / f23r )**2
     *          + ( s13 / f13r )**2
         else
            rd = ( s33 / f3cr )**2
     *          + ( s23 / f23r )**2
     *          + ( s13 / f13r )**2
         end if
         if ( rd .ge. one ) then
            dmgDelamination_New( k ) = one
         end if
c
        end if
c
        if ( statusMp_Old( k ) .eq. zero ) then
c
         dmgFiberT_New( k ) = dmgFiberT_Old( k ) 
         dmgFiberC_New( k ) = dmgFiberC_Old( k )
         dmgMatrixT_New( k ) = dmgMatrixT_Old( k )
         dmgMatrixC_New( k ) = dmgMatrixC_Old( k )      
         dmgDelamination_New( k ) = dmgDelamination_Old( k )
c
        end if
      end do
c
      return
        end


        subroutine Murakami( 
c     read
     *  nblock, ndir, nshr, nstatev, dt, charLength,
     *  alpha, gama, stateOld, stressNew,
     *  feft, fefc, femt, femc, fedl,  
c     write
     *  stateNew )
c
      include 'vaba_param.inc'
      dimension charLength( nblock ), stateOld( nblock, nstatev ), 
     *  stressNew( nblock, ndir + nshr ), stateNew( nblock, nstatev )
      parameter( zero = 0.d0, one = 1.d0, two = 2.d0, half = .5d0 )
      parameter( viscosity = 3.d-9)
      parameter(
     *          i_svd_statusMp = 1,
     *          i_svd_DmgFiberT = 2,
     *          i_svd_DmgFiberC = 3,
     *          i_svd_DmgMatrixT = 4,
     *          i_svd_DmgMatrixC = 5,
     *          i_svd_DmgDelamination = 6,
     *          i_svd_dampStress = 7,
c                 * i_svd_dampStressXx = 7,
c                 * i_svd_dampStressYy = 8,
c                 * i_svd_dampStressZz = 9,
c                 * i_svd_dampStressXy = 10,
c                 * i_svd_dampStressYz = 11,
c                 * i_svd_dampStressZx = 12,
     *          i_svd_Strain = 13,
c                 * i_svd_StrainXx = 13,
c                 * i_svd_StrainYy = 14,
c                 * i_svd_StrainZz = 15,
c                 * i_svd_StrainXy = 16,
c                 * i_svd_StrainYz = 17,
c                 * i_svd_StrainZx = 18,             
     *          i_svd_min_eq_disp_ft = 19,
     *          i_svd_min_eq_disp_fc = 20,
     *          i_svd_min_eq_disp_mt = 21,
     *          i_svd_min_eq_disp_mc = 22,
     *          i_svd_min_eq_disp_dl = 23,
     *          i_svd_max_eq_disp_ft = 24,
     *          i_svd_max_eq_disp_fc = 25,
     *          i_svd_max_eq_disp_mt = 26,
     *          i_svd_max_eq_disp_mc = 27,
     *          i_svd_max_eq_disp_dl = 28,     
     *          i_svd_dft = 29,
     *          i_svd_dfc = 30,
     *          i_svd_dmt = 31,
     *          i_svd_dmc = 32,
     *          i_svd_dlt = 33,     
     *          i_svd_dlc = 34,
     *          i_svd_dft_novis =35,
     *          i_svd_dfc_novis =36,
     *          i_svd_dmt_novis =37,
     *          i_svd_dmc_novis =38,
     *          i_svd_del_novis =39 )
      double precision min_eq_disp, max_eq_disp
      do k = 1, nblock
         lc = charLength( k )
         stateNew( k, i_svd_min_eq_disp_ft ) = 
     1                              stateOld( k, i_svd_min_eq_disp_ft )
         stateNew( k, i_svd_min_eq_disp_fc ) = 
     1                              stateOld( k, i_svd_min_eq_disp_fc )
         stateNew( k, i_svd_min_eq_disp_mt ) = 
     1                              stateOld( k, i_svd_min_eq_disp_mt )
         stateNew( k, i_svd_min_eq_disp_mc ) = 
     1                              stateOld( k, i_svd_min_eq_disp_mc )
         stateNew( k, i_svd_min_eq_disp_dl ) = 
     1                              stateOld( k, i_svd_min_eq_disp_dl )
         stateNew( k, i_svd_max_eq_disp_ft ) = 
     1                              stateOld( k, i_svd_max_eq_disp_ft )
         stateNew( k, i_svd_max_eq_disp_fc ) = 
     1                              stateOld( k, i_svd_max_eq_disp_fc ) 
         stateNew( k, i_svd_max_eq_disp_mt ) = 
     1                              stateOld( k, i_svd_max_eq_disp_mt )
         stateNew( k, i_svd_max_eq_disp_mc ) = 
     1                              stateOld( k, i_svd_max_eq_disp_mc )
         stateNew( k, i_svd_max_eq_disp_dl ) = 
     1                              stateOld( k, i_svd_max_eq_disp_dl )
         e11 = stateNew( k, i_svd_strain + 0 )
         e22 = stateNew( k, i_svd_strain + 1 )
         e33 = stateNew( k, i_svd_strain + 2 )
         e12 = stateNew( k, i_svd_strain + 3 )
         e23 = stateNew( k, i_svd_strain + 4 )
         e13 = stateNew( k, i_svd_strain + 5 ) 
         s11 = stressNew( k, 1 )
         s22 = stressNew( k, 2 )
         s33 = stressNew( k, 3 )
         s12 = stressNew( k, 4 )
         s23 = stressNew( k, 5 )
         s13 = stressNew( k, 6 )
c
c     Calculate min- and max- equivalent displacement
         if ( stateOld( k, i_svd_DmgFiberT ) .eq. zero 
     *       .and. stateNew( k, i_svd_DmgFiberT ) .eq. one ) then
            min_eq_disp = lc * 
     *                    sqrt( e11**2 + alpha * ( e12**2 + e13**2 ) )
            eq_stress = lc / min_eq_disp
     *        * ( abs(s11*e11) + alpha*(abs(s12*e12)+abs(s13 * e13)) )
            max_eq_disp = two * feft / eq_stress
            max_eq_disp = max(
     *         max_eq_disp, min_eq_disp * (one + 1.d-6))
            stateNew( k, i_svd_min_eq_disp_ft ) = min_eq_disp
            stateNew( k, i_svd_max_eq_disp_ft ) = max_eq_disp
         end if 
c
         if ( stateOld( k, i_svd_DmgFiberC ) .eq. zero 
     *       .and. stateNew( k, i_svd_DmgFiberC ) .eq. one ) then
            min_eq_disp = lc *
     *                    sqrt( e11**2 + e12**2 + e13**2 )
            eq_stress = lc / min_eq_disp
     *        * ( abs(s11*e11) + abs(s12*e12) + abs(s13*e13) )
            max_eq_disp = two * fefc / eq_stress   
            max_eq_disp = max(
     *         max_eq_disp, min_eq_disp * (one + 1.d-6))
            stateNew( k, i_svd_min_eq_disp_fc ) = min_eq_disp
            stateNew( k, i_svd_max_eq_disp_fc ) = max_eq_disp
         end if
c
         if ( stateOld( k, i_svd_DmgMatrixT ) .eq. zero 
     *       .and. stateNew( k, i_svd_DmgMatrixT ) .eq. one ) then
            min_eq_disp = lc * 
     *                    sqrt( e22**2 + gama*e12**2 + gama*e23**2 )
            eq_stress = lc / min_eq_disp
     *        * ( abs(s22*e22) + gama*abs(s12*e12) + gama*abs(s23*e23))
            max_eq_disp = two * femt / eq_stress
            max_eq_disp = max(
     *         max_eq_disp, min_eq_disp * (one + 1.d-6))
            stateNew( k, i_svd_min_eq_disp_mt ) = min_eq_disp
            stateNew( k, i_svd_max_eq_disp_mt ) = max_eq_disp
         end if
c
         if ( stateOld( k, i_svd_DmgMatrixC ) .eq. zero 
     *       .and. stateNew( k, i_svd_DmgMatrixC ) .eq. one ) then
            min_eq_disp = lc * sqrt( e22**2 + e12**2 + e23**2 )
            eq_stress = lc / min_eq_disp 
     *        * ( abs(s22*e22) + abs(s12*e12) + abs(s23*e23) )
            max_eq_disp = two * femc / eq_stress
            max_eq_disp = max(
     *         max_eq_disp, min_eq_disp * (one + 1.d-6))
            stateNew( k, i_svd_min_eq_disp_mc ) = min_eq_disp
            stateNew( k, i_svd_max_eq_disp_mc ) = max_eq_disp
         end if
c        
         if ( stateOld( k, i_svd_DmgDelamination ) .eq. zero
     *       .and. stateNew( k, i_svd_DmgDelamination ) .eq. one ) then
            min_eq_disp = lc * 
     *                    sqrt( e33**2 + alpha * ( e23**2 + e13**2 ) )
            eq_stress = lc / min_eq_disp
     *        * ( abs(s33*e33) + alpha*( abs(s23*e23)+abs(s13*e13) ) )
            max_eq_disp = two * fedl / eq_stress
            max_eq_disp = max(
     *         max_eq_disp, min_eq_disp * (one + 1.d-6))
            stateNew( k, i_svd_min_eq_disp_dl ) = min_eq_disp
            stateNew( k, i_svd_max_eq_disp_dl ) = max_eq_disp
         end if
c
c     Update damage state variables for old damages and store 
c       new damage in stateNew
         if ( stateNew( k, i_svd_DmgFiberT ) .eq. one ) then
            min_eq_disp = stateNew( k, i_svd_min_eq_disp_ft )
            max_eq_disp = stateNew( k, i_svd_max_eq_disp_ft )
            eq_disp = lc * sqrt( e11**2 + alpha * ( e12**2 + e13**2 ) )
            dft = max_eq_disp * ( eq_disp - min_eq_disp )
     *            / ( eq_disp * ( max_eq_disp - min_eq_disp ) )
            dft = max( zero, min( dft, one ) )
            stateNew( k, i_svd_dft_novis ) =
     *              max( dft , stateOld( k, i_svd_dft_novis ) )
            stateNew( k, i_svd_dft ) = dt / ( dt + viscosity ) 
     *              * stateNew( k, i_svd_dft_novis )
     *              + viscosity / ( dt + viscosity )
     *              * stateOld( k, i_svd_dft )
         end if
c
         if ( stateNew( k, i_svd_DmgFiberC ) .eq. one ) then
            min_eq_disp = stateNew( k, i_svd_min_eq_disp_fc )
            max_eq_disp = stateNew( k, i_svd_max_eq_disp_fc )
            eq_disp = lc * sqrt( e11**2 + e12**2 + e13**2 )
            dfc = max_eq_disp * ( eq_disp - min_eq_disp )
     *            / ( eq_disp * ( max_eq_disp - min_eq_disp ) )
            dfc = max( zero, min( dfc, one ) ) 
            stateNew( k, i_svd_dfc_novis ) =
     *              max( dfc , stateOld( k, i_svd_dfc_novis ) )
            stateNew( k, i_svd_dfc ) = dt / ( dt + viscosity ) 
     *              * stateNew( k, i_svd_dfc_novis )
     *              + viscosity / ( dt + viscosity )
     *              * stateOld( k, i_svd_dfc )
         end if
c
         if ( stateNew( k, i_svd_DmgMatrixT ) .eq. one ) then
            min_eq_disp = stateNew( k, i_svd_min_eq_disp_mt )
            max_eq_disp = stateNew( k, i_svd_max_eq_disp_mt )
            eq_disp = lc * sqrt( e22**2 + gama*e12**2 + gama*e23**2 )
            dmt = max_eq_disp * ( eq_disp - min_eq_disp )
     *             / ( eq_disp * ( max_eq_disp - min_eq_disp ) )
            dmt = max( zero, min( dmt, one ) )
            stateNew( k, i_svd_dmt_novis ) =
     *              max( dmt , stateOld( k, i_svd_dmt_novis ) )
            stateNew( k, i_svd_dmt ) = dt / ( dt + viscosity ) 
     *            * stateNew( k, i_svd_dmt_novis )
     *            + viscosity / ( dt + viscosity )
     *            * stateOld( k, i_svd_dmt )
         end if
c
         if ( stateNew( k, i_svd_DmgMatrixC ) .eq. one ) then
            min_eq_disp = stateNew( k, i_svd_min_eq_disp_mc )
            max_eq_disp = stateNew( k, i_svd_max_eq_disp_mc )          
            eq_disp = lc * sqrt( e22**2 + e12**2 + e23**2 )
            dmc = max_eq_disp * ( eq_disp - min_eq_disp )
     *            / ( eq_disp * ( max_eq_disp - min_eq_disp ) )
            dmc = max( zero, min( dmc, one ) )
            stateNew( k, i_svd_dmc_novis ) =
     *              max( dmc , stateOld( k, i_svd_dmc_novis ) )
            stateNew( k, i_svd_dmc ) = dt / ( dt + viscosity ) 
     *            * stateNew( k, i_svd_dmc_novis )
     *            + viscosity / ( dt + viscosity )
     *            * stateOld( k, i_svd_dmc )
         end if
c
         if ( stateNew( k, i_svd_DmgDelamination ) .eq. one ) then
            min_eq_disp = stateNew( k, i_svd_min_eq_disp_dl )
            max_eq_disp = stateNew( k, i_svd_max_eq_disp_dl )         
            eq_disp = lc * sqrt( e33**2 + alpha * ( e23**2 + e13**2 ) )
            dlt =  max_eq_disp * ( eq_disp - min_eq_disp )
     *             / ( eq_disp * ( max_eq_disp - min_eq_disp ) )
            dlt = max( zero, min( dlt, one ) )
            stateNew( k, i_svd_del_novis ) =
     *              max( dlt , stateOld( k, i_svd_del_novis ) )
            stateNew( k, i_svd_dlt ) = dt / ( dt + viscosity ) 
     *            * stateNew( k, i_svd_del_novis )
     *            + viscosity / ( dt + viscosity )
     *            * stateOld( k, i_svd_dlt )
         end if
      end do
c
      return
        end


        subroutine EnergyInternal3d(nblock, sigOld, sigNew ,
     *  strainInc, curDensity, enerInternOld, enerInternNew)
c
      include 'vaba_param.inc'
      parameter(
     *          i_Xx = 1,
     *          i_Yy = 2,
     *          i_Zz = 3,
     *          i_Xy = 4,
     *          i_Yz = 5,
     *          i_Zx = 6,
     *          n_Car = 6 )
      parameter( two = 2.d0, half = .5d0 )
      dimension sigOld( nblock, n_Car ), sigNew( nblock, n_Car ),
     *  strainInc( nblock, n_Car ), curDensity( nblock ),
     *  enerInternOld( nblock ), enerInternNew( nblock )
c
      do k = 1, nblock
         stressPower = 
     *    ( sigOld(k,i_Xx) + sigNew(k,i_Xx) ) * strainInc(k,i_Xx)
     *  + ( sigOld(k,i_Yy) + sigNew(k,i_Yy) ) * strainInc(k,i_Yy)
     *  + ( sigOld(k,i_Zz) + sigNew(k,i_Zz) ) * strainInc(k,i_Zz)
     *  + two * ( sigOld(k,i_Xy) + sigNew(k,i_Xy) ) * strainInc(k,i_Xy)
     *  + two * ( sigOld(k,i_Yz) + sigNew(k,i_Yz) ) * strainInc(k,i_Yz)
     *  + two * ( sigOld(k,i_Zx) + sigNew(k,i_Zx) ) * strainInc(k,i_Zx)
        enerInternNew(k) = enerInternOld(k)
     *                    + half * stressPower / curDensity(k)
      end do
c
      return
      end


        subroutine EnergyInelastic3d(nblock, sigNew, strain,
     *  curDensity, enerInternNew, enerInelasOld, enerInelasNew)
c
c     Report the irreversible part of the accumulated stress work.  This
c     does not change the constitutive response; it makes VUMAT dissipation
c     visible in Abaqus energy output and prevents it from being mistaken
c     for recoverable elastic energy.
c
      include 'vaba_param.inc'
      parameter( zero = 0.d0, half = .5d0, two = 2.d0 )
      parameter(
     *          i_Xx = 1,
     *          i_Yy = 2,
     *          i_Zz = 3,
     *          i_Xy = 4,
     *          i_Yz = 5,
     *          i_Zx = 6,
     *          n_Car = 6 )
      dimension sigNew(nblock,n_Car), strain(nblock,n_Car),
     *  curDensity(nblock), enerInternNew(nblock),
     *  enerInelasOld(nblock), enerInelasNew(nblock)
c
      do k = 1, nblock
         elasticSpecific = half * (
     *      sigNew(k,i_Xx) * strain(k,i_Xx)
     *    + sigNew(k,i_Yy) * strain(k,i_Yy)
     *    + sigNew(k,i_Zz) * strain(k,i_Zz)
     *    + two * sigNew(k,i_Xy) * strain(k,i_Xy)
     *    + two * sigNew(k,i_Yz) * strain(k,i_Yz)
     *    + two * sigNew(k,i_Zx) * strain(k,i_Zx) )
     *    / curDensity(k)
         dissipatedSpecific = max(
     *      zero, enerInternNew(k) - elasticSpecific)
         enerInelasNew(k) = max(
     *      enerInelasOld(k), dissipatedSpecific)
      end do
c
      return
      end


        subroutine eig33Anal( nblock, sMat, eigVal )
c
      include 'vaba_param.inc'
      parameter( i_s33_Xx=1,i_s33_Yy=2,i_s33_Zz=3 )
      parameter( i_s33_Xy=4,i_s33_Yz=5,i_s33_Zx=6 )
      parameter( i_s33_Yx=i_s33_Xy )
      parameter( i_s33_Zy=i_s33_Yz )
      parameter( i_s33_Xz=i_s33_Zx )
      parameter( i_v3d_X=1,i_v3d_Y=2,i_v3d_Z=3 )
      parameter( n_v3d_Car=3,n_s33_Car=6 )
      parameter( zero = 0.d0, one = 1.d0, two = 2.d0,
     *           three = 3.d0, half = 0.5d0, third = one / three,
     *           pi23 = 2.094395102393195d0,
     *           fuzz = 1.d-8,
     *           preciz = fuzz * 1.d4 )
      dimension eigVal(nblock,n_v3d_Car), sMat(nblock,n_s33_Car)
c
      do k = 1, nblock
        sh = third*(sMat(k,i_s33_Xx)+sMat(k,i_s33_Yy)+sMat(k,i_s33_Zz))
        s11 = sMat(k,i_s33_Xx) - sh
        s22 = sMat(k,i_s33_Yy) - sh
        s33 = sMat(k,i_s33_Zz) - sh
        s12 = sMat(k,i_s33_Xy)
        s13 = sMat(k,i_s33_Xz)
        s23 = sMat(k,i_s33_Yz)
        fac = max(abs(s11), abs(s22), abs(s33))
        facs = max(abs(s12), abs(s13), abs(s23))
        if( facs .lt. (preciz*fac) ) then
          eigVal(k,i_v3d_X) = sMat(k,i_s33_Xx)
          eigVal(k,i_v3d_Y) = sMat(k,i_s33_Yy)
          eigVal(k,i_v3d_Z) = sMat(k,i_s33_Zz)
        else
          q = third*((s12**2+s13**2+s23**2)+half*(s11**2+s22**2+s33**2))
          fac = two * sqrt(q)
          if( fac .gt. fuzz ) then
            ofac = two/fac
          else
            ofac = zero
          end if
          s11 = ofac*s11
          s22 = ofac*s22
          s33 = ofac*s33
          s12 = ofac*s12
          s13 = ofac*s13
          s23 = ofac*s23
          r = s12*s13*s23
     *        + half*(s11*s22*s33-s11*s23**2-s22*s13**2-s33*s12**2)
          if( r .ge. one-fuzz ) then
            cos1 = -half
            cos2 = -half
            cos3 = one
          else if( r .le. fuzz-one ) then
            cos1 = -one
            cos2 = half
            cos3 = half
          else
            ang = third * acos(r)
            cos1 = cos(ang)
            cos2 = cos(ang+pi23)
            cos3 =-cos1-cos2
          end if
          eigVal(k,i_v3d_X) = sh + fac*cos1
          eigVal(k,i_v3d_Y) = sh + fac*cos2
          eigVal(k,i_v3d_Z) = sh + fac*cos3
        end if
      end do
c
      return
        end


        subroutine UpdateStrain ( nblock,
     *  strainInc, strainOld, strainNew )
c
      include 'vaba_param.inc'
      parameter(
     *          i_s33_Xx = 1,
     *          i_s33_Yy = 2,
     *          i_s33_Zz = 3,
     *          i_s33_Xy = 4,
     *          i_s33_Yz = 5,
     *          i_s33_Zx = 6,
     *          n_s33_Car = 6 )
      dimension strainInc(nblock,n_s33_Car),
     *          strainOld(nblock,n_s33_Car),
     *          strainNew(nblock,n_s33_Car)
      do k = 1, nblock
         strainNew(k,i_s33_Xx)= strainOld(k,i_s33_Xx)
     *                        + strainInc(k,i_s33_Xx)
         strainNew(k,i_s33_Yy)= strainOld(k,i_s33_Yy)
     *                        + strainInc(k,i_s33_Yy)
         strainNew(k,i_s33_Zz)= strainOld(k,i_s33_Zz)
     *                        + strainInc(k,i_s33_Zz)
         strainNew(k,i_s33_Xy)= strainOld(k,i_s33_Xy)
     *                        + strainInc(k,i_s33_Xy)
         strainNew(k,i_s33_Yz)= strainOld(k,i_s33_Yz)
     *                        + strainInc(k,i_s33_Yz)
         strainNew(k,i_s33_Zx)= strainOld(k,i_s33_Zx)
     *                        + strainInc(k,i_s33_Zx)
      end do
c
      return
        end
